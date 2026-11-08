import os
import random
from flask import Flask, request, jsonify

app = Flask(__name__)

# Игра "Камень, ножницы, бумага"
def play_game(user_choice):
    choices = ['камень', 'ножницы', 'бумага']
    bot_choice = random.choice(choices)
    
    if user_choice == bot_choice:
        return f"Ничья! Оба выбрали {user_choice}."
    elif (user_choice == 'камень' and bot_choice == 'ножницы') or \
         (user_choice == 'ножницы' and bot_choice == 'бумага') or \
         (user_choice == 'бумага' and bot_choice == 'камень'):
        return f"Вы выиграли! {user_choice} побеждает {bot_choice}."
    else:
        return f"Вы проиграли! {bot_choice} побеждает {user_choice}."

@app.route('/play', methods=['POST'])
def play():
    data = request.json
    user_choice = data.get('choice')
    
    if user_choice not in ['камень', 'ножницы', 'бумага']:
        return jsonify({'error': 'Неверный выбор. Выберите камень, ножницы или бумагу.'}), 400
    
    result = play_game(user_choice)
    return jsonify({'result': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))