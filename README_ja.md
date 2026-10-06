# EventMeet

**[Frappe](https://frappeframework.com/) 用のセミナー・社内ミーティング管理アプリ**（Frappe v15 / v16 対応）

- **セミナー**（オンライン・対面・ハイブリッド）：企画、公開の申込ページ、Stripe による有料チケット、
  申込者ごとの個別参加 URL 付きの Zoom ミーティング／ウェビナー、QR 受付、リマインド、出席の取り込み、アンケート。
- **社内ミーティング**：議題、社内・社外の参加者、招待、議事録、ToDo と連動するアクションアイテム。
  会議ツールは Zoom か Google Meet を選べます。Google Meet では主催者の Google カレンダーに予定を作り、
  Gemini の「自動メモ作成」の要約を議事録に取り込みます。

[English README](README.md)

> EventMeet は独立したオープンソースプロジェクトであり、Frappe Technologies の公式製品ではありません。
> Zoom、Google Meet、Stripe は各社の商標です。

## 開発状況

EventMeet 0.1.0 は最初の公開版です。すべての連携は外部 API をモックした自動テストで確認しており、
実際のサービスでの検証状況は次のとおりです。

| 連携 | 実サービスでの検証 |
|---|---|
| Google Meet（社内ミーティング） | 済：予定と Meet の作成、Google カレンダーの招待、出席と Gemini メモの取り込み（Frappe 16.33） |
| Zoom（セミナー） | 済（Zoom Pro）：登録制ミーティングの作成・変更・削除、個別参加 URL、ホストとして開始、終了の Webhook、出席の取り込み。ウェビナーは未検証。[Zoom 手順書](docs/ja/zoom-seminar-guide.md)を参照 |
| Stripe（有料チケット） | 未 |

ご自身の環境での動作報告を Issue でお待ちしています。

## 提供機能

| 領域 | 機能 |
|---|---|
| 企画 | セミナー（形式・日時・定員・会場）、プログラム、登壇者、準備タスク（担当者割当 → ToDo 連動） |
| 集客・申込 | 公開ページ `/seminars`、申込フォーム（チケット種別・枠数・ボット対策・レート制限） |
| 決済 | Stripe Checkout（カード／コンビニ等の非同期決済、Stripe 請求書＝領収書）、返金、Webhook 未達時の自動照合、請求書払い等の手動確定 |
| オンライン | 登録制の Zoom ミーティング／ウェビナーの自動作成・変更・取消、申込者ごとの個別参加 URL、ホストとして開始 |
| 当日 | QR 受付（`/seminar-checkin`、スタッフのみ）、リマインドメール |
| 事後 | Zoom の出席の取り込み（出席・視聴時間）、アンケート（`/seminar-feedback`） |
| 社内ミーティング | 議題・参加者・**社外参加者**（アカウント不要、メール／Google カレンダーで招待）・招待・議事録・アクションアイテム（ToDo と双方向同期）。閲覧は主催者と参加者のみ |
| Google Meet | 主催者の Google カレンダーに Meet 付きの予定を作成、招待・変更・中止は Google から通知、出席の取り込み、Gemini「自動メモ作成」の取り込み |
| Zoom ライセンス | ホストアカウントのプールから空きを自動割当（必要なライセンス数は社員数ではなく同時開催数のピーク） |

会議ツールは `eventmeet/conferencing/providers/` のインタフェースで抽象化しており、
自前の基盤（LiveKit / Jitsi など）も同じ形で追加できます。

| | Zoom | Google Meet |
|---|---|---|
| 用途 | セミナー（登録制ミーティング／ウェビナー）、社内ミーティング | 社内ミーティング |
| ホスト | ライセンス付与済みホストのプールから自動割当 | 主催者本人（Workspace ユーザー） |
| 招待 | EventMeet からメール＋ICS | Google カレンダーの招待（「招待を送信」で送出） |
| 出席 | Zoom レポート API | Meet REST API（メールは People API で特定、不可時は表示名で照合） |
| AI 要約 | Zoom AI Companion の会議要約 | Gemini「自動メモ作成」のドキュメント（任意） |

画面は日本語に翻訳済みです。

## 動作環境

| | |
|---|---|
| Frappe | v15 または v16（ERPNext は不要） |
| Python | 3.10 以降 |
| Zoom | Server-to-Server OAuth アプリとライセンス付与済みのホストユーザーがある有料アカウント（セミナーや Zoom 会議を使う場合） |
| Google Workspace | ドメイン全体の委任を設定したサービスアカウント（Google Meet を使う場合） |
| Stripe | 有料チケットを販売する場合のみ |

## インストール

```bash
bench get-app https://github.com/lifegence/eventmeet
bench --site <site> install-app eventmeet
bench --site <site> migrate
```

インストール後、System Manager で「オンライン会議設定」と「セミナー設定」を開いて設定します。

## セットアップ

### Zoom

初回の検証手順を含む詳しい手順は [docs/ja/zoom-seminar-guide.md](docs/ja/zoom-seminar-guide.md) を参照してください。概要:

1. Zoom App Marketplace で **Server-to-Server OAuth** アプリを作成し、手順書に記載のスコープ
   （`eventmeet/conferencing/providers/zoom.py` の冒頭にも記載）を追加
2. Event Subscription を有効化：URL `https://<site>/api/method/eventmeet.api.webhooks.zoom`、
   イベント `meeting.ended` / `webinar.ended` /（任意）`meeting.summary_completed`。
   「Validate」を押す前に Secret Token を Frappe に保存しておく
3. 「オンライン会議設定」にアカウント ID / クライアントID / クライアントシークレット / Webhook Secret Token を登録
4. ライセンス付与済みのユーザーを「Zoom ホストアカウント」に登録（ウェビナーのアドオンがあれば「ウェビナー上限人数」を設定）
5. 社内ミーティングの AI 要約を取り込む場合は、Zoom 側で AI Companion の会議要約を有効化

### Google Meet（社内ミーティング）

詳しい手順（どの管理画面で作業するか、動作確認、トラブルシューティング）は
[docs/ja/google-meet-setup.md](docs/ja/google-meet-setup.md) を参照してください。概要:

1. Google Cloud コンソールでサービスアカウントと JSON 鍵を作成し、Google Calendar API / Google Meet REST API /
   People API（Gemini メモを取り込む場合は Google Drive API も）を有効化
2. Google 管理コンソールの「セキュリティ」→「アクセスとデータ管理」→「API の制御」→「ドメイン全体の委任を管理」で、
   サービスアカウントのクライアント ID に次のスコープを付与
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/meetings.space.readonly`
   - `https://www.googleapis.com/auth/directory.readonly`
   - `https://www.googleapis.com/auth/drive.readonly`（Gemini メモを取り込む場合のみ）
3. 「オンライン会議設定」で Google Meet を有効化し、JSON 鍵と Workspace ドメインを登録。
   社内ミーティングの既定を Google Meet にする場合は「社内ミーティングの会議ツール」を変更
4. 主催者（Frappe ユーザー）のメールアドレスは Workspace アカウントと一致している必要があります

### Stripe

1. 「セミナー設定」に Secret Key と Webhook 署名シークレットを登録
2. Webhook：`https://<site>/api/method/eventmeet.api.webhooks.stripe`、
   イベント `checkout.session.completed` / `checkout.session.expired` /
   `checkout.session.async_payment_succeeded` / `checkout.session.async_payment_failed`
3. 領収書（適格請求書）を発行する場合は、Stripe 側で登録番号と請求書の設定を行う

### ロール

| ロール | できること |
|---|---|
| System Manager / Seminar Manager | オンライン会議設定・セミナー設定・Zoom ホストアカウントの変更、セミナーと申込の管理、セミナーをホストとして開始 |
| Seminar Staff | セミナーの閲覧、申込の閲覧・更新、当日の受付 |
| すべてのデスクユーザー | 自分が主催する社内ミーティングの作成 |

社内ミーティングを閲覧できるのは、主催者・参加者・Manager だけです。主催者以外の参加者は議事録と
アクションアイテムを編集できますが、日時・参加者・議題の変更と招待の送信はできません。
主催者を変更できるのは Seminar Manager だけです。

## 開発

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app eventmeet
```

テストでは Zoom / Google / Stripe をモックしています。lint とプルリクエストについては
[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## セキュリティ

脆弱性は公開の Issue ではなく非公開で報告してください（[SECURITY.md](SECURITY.md)）。
ゲストが到達できるエンドポイントの認可・入力検証・レート制限は
[docs/security/guest-endpoint-audit.md](docs/security/guest-endpoint-audit.md) にまとめています。

## ライセンス

[MIT](license.txt) © 2026 Lifegence Corporation
