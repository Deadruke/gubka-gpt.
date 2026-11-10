"""
CS2 Clip Maker - Backend Logic
Логика создания клипов из видео с CS2
"""

import os
import subprocess
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import threading
import queue


class CS2ClipMaker:
    """Класс для создания клипов из видео"""
    
    def __init__(self, output_dir: str = "clips"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.processing = {}
        self.results = {}
        self.lock = threading.Lock()
        
    def download_video(self, youtube_url: str) -> str:
        """Скачивание видео с YouTube"""
        video_id = youtube_url.split("v=")[-1].split("&")[0]
        output_path = self.output_dir / f"temp_{video_id}.mp4"
        
        cmd = [
            "yt-dlp",
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            youtube_url
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise Exception(f"Ошибка скачивания: {result.stderr}")
            
            if not output_path.exists():
                raise Exception("Файл не создан")
            
            return str(output_path)
            
        except subprocess.TimeoutExpired:
            raise Exception("Время ожидания скачивания истекло")
        except Exception as e:
            raise Exception(f"Ошибка скачивания: {str(e)}")
    
    def analyze_video(self, video_path: str) -> List[Dict]:
        """Анализ видео для поиска интересных моментов CS2"""
        # В реальном проекте здесь использовался бы AI для анализа
        # Для демо возвращаем случайные моменты
        import random
        
        # Получаем длительность видео
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            duration = json.loads(result.stdout)["format"]["duration"]
        except:
            duration = 300  # По умолчанию 5 минут
        
        # Генерируем случайные моменты (60-120 секунд)
        clips = []
        num_clips = random.randint(2, 4)
        
        for i in range(num_clips):
            start = random.uniform(0, duration - 120)
            end = min(start + random.uniform(60, 120), duration)
            
            clips.append({
                "id": str(uuid.uuid4()),
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "confidence": round(random.uniform(0.7, 0.99), 2)
            })
        
        return clips
    
    def create_clip(self, video_path: str, clip_info: Dict, output_path: str) -> bool:
        """Создание клипа с FFmpeg"""
        try:
            # Вырезаем фрагмент
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-ss", str(clip_info["start"]),
                "-t", str(clip_info["duration"]),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "medium",
                "-crf", "23",
                "-movflags", "+faststart",
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            print("Время ожидания FFmpeg истекло")
            return False
        except Exception as e:
            print(f"Ошибка создания клипа: {str(e)}")
            return False
    
    def add_blurred_background(self, clip_path: str, output_path: str) -> bool:
        """Добавление размытого фона"""
        try:
            # Создаем размытую копию
            temp_bg = self.output_dir / f"bg_{uuid.uuid4()}.mp4"
            
            cmd = [
                "ffmpeg",
                "-i", clip_path,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "28",
                "-y",
                str(temp_bg)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                return False
            
            # Комбинируем оригинал и фон
            cmd = [
                "ffmpeg",
                "-i", clip_path,
                "-i", str(temp_bg),
                "-filter_complex",
                "[0:v][1:v]overlay=(W-w)/2:(H-h)/2",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-movflags", "+faststart",
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Удаляем временный файл
            if temp_bg.exists():
                temp_bg.unlink()
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"Ошибка добавления фона: {str(e)}")
            return False
    
    def add_subtitles(self, video_path: str, output_path: str) -> bool:
        """Добавление субтитров с помощью Whisper"""
        try:
            # Создаем временный файл с субтитрами
            srt_path = self.output_dir / f"subs_{uuid.uuid4()}.srt"
            
            # Генерируем временные субтитры (для демо)
            srt_content = self._generate_sample_subtitles(clip_info)
            
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            
            # Добавляем субтитры к видео
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vf", f"subtitles='{srt_path}':force_style='Fontname=Arial,FontSize=48,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=3,Alignment=2'",
                "-c:a", "copy",
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Удаляем временный файл
            if srt_path.exists():
                srt_path.unlink()
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"Ошибка добавления субтитров: {str(e)}")
            return False
    
    def _generate_sample_subtitles(self, clip_info: Dict) -> str:
        """Генерация примерных субтитров"""
        start = clip_info["start"]
        end = clip_info["end"]
        duration = clip_info["duration"]
        
        # Генерируем субтитры с примерным текстом
        subtitles = []
        current_time = start
        
        while current_time < end:
            next_time = min(current_time + 3, end)
            
            subtitle = f"""1
{self._format_timestamp(current_time)} --> {self._format_timestamp(next_time)}
CS2 Highlights - Amazing Moments

2
{self._format_timestamp(next_time)} --> {self._format_timestamp(min(next_time + 3, end))}
Best plays and clips

"""
            subtitles.append(subtitle)
            current_time = next_time
        
        return "".join(subtitles)
    
    def _format_timestamp(self, seconds: float) -> str:
        """Форматирование времени в формат SRT"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def process_clip(self, youtube_url: str, clip_id: str) -> Dict:
        """Полная обработка клипа"""
        task_id = str(uuid.uuid4())
        
        with self.lock:
            self.processing[task_id] = {
                "status": "processing",
                "progress": 0,
                "youtube_url": youtube_url,
                "clip_id": clip_id,
                "created_at": datetime.now().isoformat()
            }
        
        try:
            # 1. Скачивание видео
            with self.lock:
                self.processing[task_id]["progress"] = 10
                self.processing[task_id]["status"] = "downloading"
            
            video_path = self.download_video(youtube_url)
            
            # 2. Анализ видео
            with self.lock:
                self.processing[task_id]["progress"] = 30
                self.processing[task_id]["status"] = "analyzing"
            
            clips = self.analyze_video(video_path)
            
            # 3. Создание клипов
            with self.lock:
                self.processing[task_id]["progress"] = 50
                self.processing[task_id]["status"] = "creating_clips"
            
            clip_results = []
            
            for clip_info in clips:
                clip_output = self.output_dir / f"clip_{clip_id}_{clip_info['id']}.mp4"
                
                # Создаем клип
                if self.create_clip(video_path, clip_info, str(clip_output)):
                    # Добавляем фон
                    final_output = self.output_dir / f"clip_{clip_id}_{clip_info['id']}_final.mp4"
                    
                    if self.add_blurred_background(str(clip_output), str(final_output)):
                        # Добавляем субтитры
                        if self.add_subtitles(str(final_output), str(clip_output)):
                            clip_output.unlink()
                            clip_output = final_output
                    
                    clip_results.append({
                        "id": clip_info["id"],
                        "path": str(clip_output),
                        "duration": clip_info["duration"],
                        "start": clip_info["start"],
                        "end": clip_info["end"]
                    })
            
            # 4. Завершение
            with self.lock:
                self.processing[task_id]["progress"] = 100
                self.processing[task_id]["status"] = "completed"
                self.processing[task_id]["result"] = clip_results
            
            return {
                "task_id": task_id,
                "status": "completed",
                "clips": clip_results
            }
            
        except Exception as e:
            with self.lock:
                self.processing[task_id]["status"] = "failed"
                self.processing[task_id]["error"] = str(e)
            
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e)
            }
    
    def get_processing_status(self, task_id: str) -> Optional[Dict]:
        """Получение статуса обработки"""
        with self.lock:
            return self.processing.get(task_id)
    
    def get_all_clips(self) -> List[Dict]:
        """Получение всех готовых клипов"""
        clips = []
        
        for clip_file in self.output_dir.glob("clip_*.mp4"):
            stat = clip_file.stat()
            clips.append({
                "id": clip_file.stem.replace("clip_", ""),
                "path": str(clip_file),
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
        
        return clips
    
    def delete_clip(self, clip_id: str) -> bool:
        """Удаление клипа"""
        with self.lock:
            for clip_file in self.output_dir.glob(f"clip_{clip_id}*.mp4"):
                try:
                    clip_file.unlink()
                except:
                    pass
        
        return True


# Глобальный экземпляр
clip_maker = CS2ClipMaker()