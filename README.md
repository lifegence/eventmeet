# EventMeet

**Seminar & internal meeting management for Frappe** — セミナー（オンライン / オフライン / ハイブリッド）の
企画・集客・決済・当日運営・事後フォローと、社内ミーティング（議題・議事録・アクション管理）を
ひとつのアプリで扱う Frappe アプリ。Frappe **v15 / v16** 両対応。MIT ライセンス。

> EventMeet は独立したオープンソースプロジェクトであり、Frappe Technologies の公式製品ではありません。
> Zoom、Google Meet、Stripe は各社の商標です。

## 提供機能

| 領域 | 機能 |
|---|---|
| 企画 | セミナー（形式・日時・定員・会場）、プログラム、登壇者、準備タスク（担当者割当 → ToDo 連動） |
| 集客・申込 | 公開ページ `/seminars`、申込フォーム（チケット種別・枠数・ボット対策・レート制限） |
| 決済 | Stripe Checkout（カード / コンビニ等の非同期決済、Stripe 請求書 = 領収書）、返金、Webhook 未達時の自動照合、請求書払い等の手動確定 |
| オンライン | Zoom Meeting（登録制）/ Webinar の自動作成・変更・取消、申込者ごとの個別参加 URL、ホストとして開始 |
| 当日 | QR チェックイン（`/seminar-checkin`、スタッフのみ）、リマインドメール |
| 事後 | Zoom 参加ログ取込（出席・視聴分数）、アンケート（`/seminar-feedback`） |
| 社内 MTG | 議題・参加者・**社外参加者**（アカウント不要、メール / Google カレンダーで招待）・招待・議事録・アクション（ToDo 双方向同期）・参加者のみ閲覧可。会議ツールは **Zoom / Google Meet** を選択 |
| Google Meet | 主催者の Google カレンダーに予定 + Meet を作成、Google から招待・変更・中止を通知、参加ログ取込、Gemini「自動メモ作成」の議事録取込 |
| Zoom ライセンス | ホストアカウントのプールから空きを自動割当（必要ライセンス数 = 同時開催数のピーク） |

会議基盤は `eventmeet/conferencing/providers/` のインタフェースで抽象化しており、
自前の WebRTC 基盤（LiveKit / Jitsi 等）も同じ形で追加できる。

| | Zoom | Google Meet |
|---|---|---|
| 用途 | セミナー（登録制 Meeting / Webinar）、社内 MTG | 社内 MTG |
| ホスト | ライセンス付与済みホストのプールから自動割当 | 主催者本人（Workspace ユーザー） |
| 招待 | アプリからメール + ICS | Google カレンダーの招待（アプリの「招待を送信」で送出） |
| 参加ログ | Zoom レポート API | Meet REST API（参加者 → People API でメール解決、不可時は表示名で照合） |
| AI 議事録 | AI Companion 会議要約 | Gemini「自動メモ作成」ドキュメント（任意） |

## 構成

```
eventmeet/
├── seminar/        Seminar, Registration, Ticket Type, Session, Task, Speaker, Venue, Feedback, Settings
├── meeting/        Internal Meeting (+ Agenda / Attendee / Action)
├── conferencing/   Conference Session, Zoom Host Account, Conferencing Settings, providers/
├── services/       registration, conference, host_pool, stripe_api, notifications, todo_sync
├── api/            public (guest), staff, conference, webhooks
└── www/            seminars, seminar-registration, seminar-checkin, seminar-feedback
```

## セットアップ

```bash
bench get-app <repo-url>
bench --site <site> install-app eventmeet
```

### Zoom
1. Zoom App Marketplace で **Server-to-Server OAuth** アプリを作成し、`zoom.py` 冒頭のスコープを付与
2. Event Subscription を有効化: URL `https://<site>/api/method/eventmeet.api.webhooks.zoom`、
   イベント `meeting.ended` / `webinar.ended` / `meeting.summary_completed`
3. **Conferencing Settings** に Account ID / Client ID / Client Secret / Secret Token を登録
4. **Zoom Host Account** にライセンス付与済みユーザーを登録（Webinar アドオンがあれば `Webinar Capacity` を設定）
5. AI 要約を取り込む場合は Zoom 側で AI Companion の会議要約を有効化

### Google Meet（社内 MTG）
詳細な手順（管理コンソールの画面操作、動作確認、トラブルシューティング）は
[docs/setup/20260929_GoogleWorkspaceSetupGuide_JA_v1.1_Draft.docx](docs/setup/20260929_GoogleWorkspaceSetupGuide_JA_v1.1_Draft.docx) を参照。

1. Google Cloud でサービスアカウントを作成し、JSON 鍵を発行。Calendar API / Google Meet REST API /
   People API（メモ取込時は Drive API）を有効化
2. Google 管理コンソール → セキュリティ → API の制御 → **ドメイン全体の委任** で、サービスアカウントの
   クライアント ID に以下のスコープを付与
   - `https://www.googleapis.com/auth/calendar.events`
   - `https://www.googleapis.com/auth/meetings.space.readonly`
   - `https://www.googleapis.com/auth/directory.readonly`
   - `https://www.googleapis.com/auth/drive.readonly`（Gemini メモを取り込む場合のみ）
3. **Conferencing Settings** で Google Meet を有効化し、JSON 鍵と Workspace ドメインを登録。
   社内 MTG の既定を Google Meet にする場合は `Internal Meeting Provider` を変更
4. 主催者（Frappe ユーザー）のメールアドレスは Workspace アカウントと一致している必要がある

### Stripe
1. **Seminar Settings** に Secret Key と Webhook Signing Secret を登録
2. Webhook: `https://<site>/api/method/eventmeet.api.webhooks.stripe`、
   イベント `checkout.session.completed` / `checkout.session.expired` /
   `checkout.session.async_payment_succeeded` / `checkout.session.async_payment_failed`
3. 領収書（適格請求書）を発行する場合は Stripe 側で登録番号・請求書設定を行う

### ロール
- **Seminar Manager**: セミナー・申込・設定の管理
- **Seminar Staff**: 閲覧と当日チェックイン
- 社内 MTG は全デスクユーザーが作成可（主催者は自分のみ。主催者の変更は Manager のみ）。
  閲覧は主催者・参加者（と Manager）のみ。主催者以外の参加者が編集できるのは議事録とアクションアイテムだけで、
  招待の送信は主催者と Manager のみ
- Conferencing Settings / Seminar Settings / Zoom Host Account は System Manager・Seminar Manager のみ

## テスト

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app eventmeet
```

外部 API（Zoom / Google / Stripe）はテストでモックする。

## セキュリティ
ゲスト到達エンドポイントの認可・入力検証・レート制限は
[docs/security/guest-endpoint-audit.md](docs/security/guest-endpoint-audit.md) を参照。

## ライセンス

[MIT License](license.txt) © 2026 Lifegence Corporation
