"""
style_bot.py — 自分の文体を再現する執筆アシスタント (Telegram常駐)

使い方:
    /x   <お題>   … Xのポストを3案
    /th  <お題>   … Xのスレッド構成＋本文
    /note <お題>  … note記事の構成＋本文
    そのまま文章を送る … 直前の出力に対する推敲指示 (例:「1案目をもっと短く」)
    /new          … 会話をリセット
    /reload       … style_card.md と examples.md を読み直す
    /style        … 現在のスタイルカードを表示
"""

import asyncio
import logging
import os
from pathlib import Path

import anthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------- 設定

BASE_DIR = Path(__file__).parent
STYLE_CARD_PATH = BASE_DIR / "style_card.md"
EXAMPLES_PATH = BASE_DIR / "examples.md"

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# 自分以外が使えないようにする。カンマ区切りで数値のユーザーIDを入れる。
# 自分のIDが分からない場合は空のままでも動くが、その場合は誰でも使える。
ALLOWED_USER_IDS = {
    int(uid) for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()
}

MODEL = "claude-sonnet-5"
MAX_TOKENS = 4000
HISTORY_TURNS = 8  # 直近何往復を文脈として保持するか

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)
log = logging.getLogger("style_bot")

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# ---------------------------------------------------------------- プロンプト

BASE_SYSTEM = """あなたは特定の書き手の専属ゴーストライターです。
その人の文体を完全に再現して原稿を書くことだけが仕事です。

絶対に守ること:
- 以下の「スタイルカード」と「お手本」を文体の唯一の基準とする。
  一般的に「良い文章」とされる形ではなく、この書き手の癖に寄せる。
- 説明・前置き・後書きを書かない。頼まれた原稿そのものだけを出力する。
- 「いかがでしたか」「〜ではないでしょうか」「〜と言えるでしょう」
  「まとめると」のような、書き手のお手本に出てこない常套句を使わない。
- 書き手が使わない記号・絵文字・見出し装飾を勝手に足さない。
- 事実関係が不明な数字や固有名詞をでっち上げない。
  必要なら [要確認: 〇〇] と明示して空欄にする。
"""

MODE_PROMPTS = {
    "x": """【今回の依頼】Xの長文ポストを2案。
- 「案1」「案2」とだけラベルを付け、本文を続ける。
- 350〜600字。短くまとめない。140字に収めようとしない。
- スタイルカードの「11. Xモード」に厳密に従う。特に:
  ・句点「。」をほぼ打たない。読点でつなぎ続ける
  ・一文を長くする。切りたくなっても切らない
  ・断定せず「〜な印象」「〜気がします」「〜と感じました」で閉じる
  ・括弧は半角 ( )
  ・最後に短いイメージの比喩を一つ置いて終わる
- 構造は 観察(具体例) → メカニズムの言語化 → だから自分はこうする、の3段。
- 挨拶・名乗り・ハッシュタグ・絵文字は入れない。
- noteの叫びや自嘲のノリをXに持ち込まない。感情は出さない。
- 2案は結論を変える。同じ主張の言い換えを2つ並べない。""",
    "th": """【今回の依頼】Xのスレッド。
- まず構成を箇条書きで出し、その下に本文を書く。
- 1ツイート目は単体で成立する引きにする。続きを読ませる仕事だけをさせる。
- 各ツイートは140字以内。ツイート間は「---」で区切り、番号を振る。
- 最後のツイートは、書き手のお手本にある締め方に合わせる。""",
    "note": """【今回の依頼】noteの記事。
- まず見出し構成案を出し、確認を待たずにそのまま本文を書ききる。
- タイトル案を3つ添える。
- 見出しの粒度・改行の量・段落の長さはスタイルカードの指定に厳密に従う。
- 導入で読む理由を作り、結論を後出しにしすぎない。""",
}


def load_context() -> str:
    """スタイルカードとお手本を読み込んでsystemプロンプトを組み立てる"""
    parts = [BASE_SYSTEM]
    for path, header in (
        (STYLE_CARD_PATH, "# スタイルカード（この書き手の文体定義）"),
        (EXAMPLES_PATH, "# お手本（この書き手が実際に書いた文章）"),
    ):
        if path.exists():
            parts.append(f"{header}\n\n{path.read_text(encoding='utf-8')}")
        else:
            log.warning("%s が見つかりません", path.name)
    return "\n\n---\n\n".join(parts)


SYSTEM_PROMPT = load_context()

# ---------------------------------------------------------------- 生成

async def generate(history: list[dict]) -> str:
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return update.effective_user and update.effective_user.id in ALLOWED_USER_IDS


def get_history(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    return context.chat_data.setdefault("history", [])


async def run(update: Update, context: ContextTypes.DEFAULT_TYPE, user_msg: str) -> None:
    history = get_history(context)
    history.append({"role": "user", "content": user_msg})
    del history[: max(0, len(history) - HISTORY_TURNS * 2)]

    typing = asyncio.create_task(keep_typing(update, context))
    try:
        answer = await generate(history)
    except anthropic.APIError as e:
        history.pop()
        log.exception("API error")
        await update.message.reply_text(f"生成に失敗しました: {e}")
        return
    finally:
        typing.cancel()

    history.append({"role": "assistant", "content": answer})

    # Telegramの1メッセージ上限は4096字
    for i in range(0, len(answer), 3900):
        await update.message.reply_text(answer[i : i + 3900])


async def keep_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """生成が終わるまで「入力中…」を出し続ける"""
    try:
        while True:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------- ハンドラ

def make_mode_handler(mode: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not allowed(update):
            return
        topic = " ".join(context.args).strip()
        if not topic:
            await update.message.reply_text(f"お題を書いてください。例: /{mode} 今日の相場")
            return
        context.chat_data["history"] = []  # モード切替時は文脈をリセット
        await run(update, context, f"{MODE_PROMPTS[mode]}\n\n【お題】\n{topic}")

    return handler


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """コマンドなしの発言は、直前の出力への推敲指示として扱う"""
    if not allowed(update):
        return
    if not get_history(context):
        await update.message.reply_text(
            "まず /x /th /note のどれかでお題をください。\n"
            "その後は普通に話しかければ推敲します。"
        )
        return
    await run(update, context, update.message.text)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data["history"] = []
    await update.message.reply_text("リセットしました。")


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = load_context()
    await update.message.reply_text(f"読み直しました（{len(SYSTEM_PROMPT)}字）。")


async def cmd_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        STYLE_CARD_PATH.read_text(encoding="utf-8")
        if STYLE_CARD_PATH.exists()
        else "style_card.md がありません。"
    )
    await update.message.reply_text(text[:3900])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "文体Bot 起動中。\n"
        "/x お題 … ポスト3案\n"
        "/th お題 … スレッド\n"
        "/note お題 … note記事\n"
        "/new リセット /reload 再読み込み /style 文体確認\n\n"
        f"あなたのユーザーID: {update.effective_user.id}"
    )


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("style", cmd_style))
    for mode in MODE_PROMPTS:
        app.add_handler(CommandHandler(mode, make_mode_handler(mode)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("起動しました")
    app.run_polling()


if __name__ == "__main__":
    main()
