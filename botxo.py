import requests
import time

TOKEN = "905198061:qafZMSlAuUyguBM1_I9k7uNniV7GIFdFkgs"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}/"


# -------------------- GAME LOGIC --------------------

class XOGame:
    def __init__(self, player1_id, player1_name):
        self.player1_id = player1_id
        self.player1_name = player1_name
        self.player2_id = None
        self.player2_name = None
        self.board = [[" "] * 3 for _ in range(3)]
        self.current_player = player1_id
        self.status = "waiting"  # waiting | playing

    def add_player2(self, player2_id, player2_name):
        self.player2_id = player2_id
        self.player2_name = player2_name
        self.status = "playing"

    def make_move(self, player_id, row, col):
        if player_id != self.current_player:
            return False, "نوبت شما نیست"

        if self.board[row][col] != " ":
            return False, "خانه پر است"

        symbol = "❌" if player_id == self.player1_id else "⭕"
        self.board[row][col] = symbol

        if self.check_winner(symbol):
            return True, "win"

        if self.is_board_full():
            return True, "draw"

        self.current_player = (
            self.player2_id if player_id == self.player1_id else self.player1_id
        )
        return True, "continue"

    def check_winner(self, symbol):
        lines = []

        lines.extend(self.board)
        lines.extend([[self.board[r][c] for r in range(3)] for c in range(3)])
        lines.append([self.board[i][i] for i in range(3)])
        lines.append([self.board[i][2 - i] for i in range(3)])

        return any(all(cell == symbol for cell in line) for line in lines)

    def is_board_full(self):
        return all(cell != " " for row in self.board for cell in row)


# -------------------- BOT --------------------

class XOBot:
    def __init__(self):
        self.active_games = {}
        self.last_update_id = 0

    def request(self, method, data=None):
        try:
            url = BASE_URL + method
            r = requests.post(url, json=data, timeout=10) if data else requests.get(url)
            return r.json()
        except:
            return {"ok": False}

    def send_message(self, chat_id, text, reply_markup=None):
        data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.request("sendMessage", data)

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }
        return self.request("editMessageText", data)

    def answer_callback(self, callback_id, text, alert=False):
        return self.request(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": text, "show_alert": alert},
        )

    def keyboard(self, chat_id, board):
        kb = []
        for i in range(3):
            row = []
            for j in range(3):
                txt = board[i][j] if board[i][j] != " " else "⬜"
                row.append({"text": txt, "callback_data": f"move_{chat_id}_{i}_{j}"})
            kb.append(row)
        kb.append([{"text": "🚫 لغو", "callback_data": f"cancel_{chat_id}"}])
        return {"inline_keyboard": kb}

    # -------------------- HANDLERS --------------------

    def handle_message(self, msg):
        text = msg.get("text")
        chat = msg["chat"]
        chat_id = chat["id"]
        chat_type = chat["type"]
        user = msg["from"]
        user_id = user["id"]
        name = user.get("first_name", "بازیکن")

        if text == "/start":
            self.send_message(chat_id, "🎮 XO Bot\n/newgame")

        if text == "/newgame":
            if chat_type == "private":
                self.send_message(chat_id, "❌ این بازی فقط در گروه قابل اجراست")
                return

            if chat_id not in self.active_games:
                self.active_games[chat_id] = XOGame(user_id, name)
                self.send_message(chat_id, f"⏳ {name} منتظر بازیکن دوم...")
                return

            game = self.active_games[chat_id]

            if game.status != "waiting":
                self.send_message(chat_id, "⚠️ بازی در حال انجام است")
                return

            if user_id == game.player1_id:
                self.send_message(chat_id, "❌ نمی‌توانید با خودتان بازی کنید")
                return

            game.add_player2(user_id, name)

            res = self.send_message(
                chat_id,
                f"🎮 <b>شروع بازی</b>\n\n❌ {game.player1_name}\n⭕ {name}",
                self.keyboard(chat_id, game.board),
            )

            if res.get("ok"):
                game.message_id = res["result"]["message_id"]

    def handle_callback(self, cb):
        data = cb["data"]
        user_id = cb["from"]["id"]
        msg = cb["message"]
        chat_id = msg["chat"]["id"]
        mid = msg["message_id"]

        if data.startswith("move_"):
            _, gid, r, c = data.split("_")
            gid, r, c = int(gid), int(r), int(c)

            if gid not in self.active_games:
                self.answer_callback(cb["id"], "بازی تمام شده", True)
                return

            game = self.active_games[gid]

            ok, result = game.make_move(user_id, r, c)
            if not ok:
                self.answer_callback(cb["id"], result, True)
                return

            if result in ("win", "draw"):
                text = "🤝 مساوی!" if result == "draw" else f"🏆 {cb['from']['first_name']} برنده شد!"
                self.edit_message(chat_id, mid, text, None)
                del self.active_games[gid]
                return

            turn = (
                game.player1_name if game.current_player == game.player1_id else game.player2_name
            )
            symbol = "❌" if game.current_player == game.player1_id else "⭕"

            self.edit_message(
                chat_id,
                mid,
                f"نوبت: {turn} ({symbol})",
                self.keyboard(gid, game.board),
            )
            self.answer_callback(cb["id"], "✔️")

        if data.startswith("cancel_"):
            gid = int(data.split("_")[1])
            if gid in self.active_games:
                del self.active_games[gid]
                self.edit_message(chat_id, mid, "🚫 بازی لغو شد", None)

    # -------------------- LOOP --------------------

    def run(self):
        print("XO Bot Running...")
        while True:
            updates = self.request("getUpdates", {
                "offset": self.last_update_id + 1,
                "timeout": 30
            })

            if updates.get("ok"):
                for u in updates["result"]:
                    self.last_update_id = u["update_id"]
                    if "message" in u:
                        self.handle_message(u["message"])
                    elif "callback_query" in u:
                        self.handle_callback(u["callback_query"])

            time.sleep(0.2)


if __name__ == "__main__":
    XOBot().run()

