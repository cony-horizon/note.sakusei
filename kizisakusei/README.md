# 文体Bot セットアップ

## 1. ファイル構成

```
style_bot/
├── bot.py           # 本体（触らなくていい）
├── style_card.md    # 文体定義。ここが心臓部。解析後に埋める
├── examples.md      # お手本。実際に書いたポスト/記事を貼る
├── requirements.txt
└── .env             # 自分で作る
```

## 2. 準備

```bash
cd style_bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 3. トークンの取得

**Telegram Bot Token**
Telegramで `@BotFather` を開く → `/newbot` → 名前とユーザー名を決める
→ 返ってきた `123456:ABC-...` がトークン。

**Anthropic API Key**
https://console.anthropic.com → Settings → API Keys → Create Key。
※ Claude.aiのサブスクとは別課金。API残高を入れておく必要がある。

## 4. .env を作る

```
TELEGRAM_BOT_TOKEN=123456:ABC-...
ANTHROPIC_API_KEY=sk-ant-...
ALLOWED_USER_IDS=
```

`ALLOWED_USER_IDS` は空のまま起動 → Botに `/start` を送ると自分のIDが返ってくるので、
それを書いて再起動する。これをやらないとURLを知った第三者が自分のAPI残高を使える。

## 5. 起動

```bash
set -a && source .env && set +a
python bot.py
```

## 6. 常駐させる

ローカルMacで動かす場合、Macを閉じると止まる。常時動かすなら:

- **Railway / Render / Fly.io** — 無料〜月数ドル。gitから直接デプロイできる。
- **VPS（さくら・ConoHa・Vultr）** — `systemd` か `tmux` で常駐。

環境変数は各サービスのダッシュボードに入れる。`.env` はgitに上げないこと
（`.gitignore` に `.env` を必ず書く）。

## 7. 使い方

| コマンド | 動作 |
|---|---|
| `/x お題` | Xポストを3案 |
| `/th お題` | Xスレッドの構成＋本文 |
| `/note お題` | note記事の構成＋本文 |
| （そのまま文章） | 直前の出力への推敲指示 |
| `/new` | 会話リセット |
| `/reload` | style_card.md / examples.md の再読み込み |
| `/style` | 現在の文体定義を確認 |

`style_card.md` を編集したら `/reload` を送るだけで反映される。再起動不要。

## 8. 育て方

出力が自分っぽくなかったら、その場で直すのではなく
**何が違ったかを `style_card.md` に1行足す**。
このループを20回くらい回すと、ほぼ自分の手癖になる。
`examples.md` も、新しく書いた自信作を足していくほど精度が上がる。
