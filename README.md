# Lifegence Seminar

オンライン/オフライン/ハイブリッドのセミナーを企画から実施・事後フォローまで支援し、
社内ミーティング（議事録・アクション管理）も扱う Frappe アプリ。Frappe **v15 / v16** 両対応。

## 提供機能

| 領域 | 機能 |
|---|---|
| 企画 | セミナー（形式・日時・定員・会場）、プログラム、登壇者、準備タスク（担当者割当 → ToDo 連動） |
| 集客・申込 | 公開ページ `/seminars`、申込フォーム（チケット種別・枠数・ボット対策・レート制限） |
| 決済 | Stripe Checkout（カード / コンビニ等の非同期決済、Stripe 請求書 = 領収書）、返金、Webhook 未達時の自動照合、請求書払い等の手動確定 |
| オンライン | Zoom Meeting（登録制）/ Webinar の自動作成・変更・取消、申込者ごとの個別参加 URL、ホストとして開始 |
| 当日 | QR チェックイン（`/seminar-checkin`、スタッフのみ）、リマインドメール |
| 事後 | Zoom 参加ログ取込（出席・視聴分数）、アンケート（`/seminar-feedback`） |
| 社内 MTG | 議題・参加者・招待メール（ICS 付き）・Zoom 自動発行・議事録・Zoom AI 要約取込・アクション（ToDo 双方向同期）・参加者のみ閲覧可 |
| Zoom ライセンス | ホストアカウントのプールから空きを自動割当（必要ライセンス数 = 同時開催数のピーク） |

会議基盤は `lifegence_seminar/conferencing/providers/` のインタフェースで抽象化しており、
Google Meet や自前 WebRTC（`lifegence_meet` 等）への差し替え・追加が可能。

## 構成

```
lifegence_seminar/
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
bench --site <site> install-app lifegence_seminar
```

### Zoom
1. Zoom App Marketplace で **Server-to-Server OAuth** アプリを作成し、`zoom.py` 冒頭のスコープを付与
2. Event Subscription を有効化: URL `https://<site>/api/method/lifegence_seminar.api.webhooks.zoom`、
   イベント `meeting.ended` / `webinar.ended` / `meeting.summary_completed`
3. **Conferencing Settings** に Account ID / Client ID / Client Secret / Secret Token を登録
4. **Zoom Host Account** にライセンス付与済みユーザーを登録（Webinar アドオンがあれば `Webinar Capacity` を設定）
5. AI 要約を取り込む場合は Zoom 側で AI Companion の会議要約を有効化

### Stripe
1. **Seminar Settings** に Secret Key と Webhook Signing Secret を登録
2. Webhook: `https://<site>/api/method/lifegence_seminar.api.webhooks.stripe`、
   イベント `checkout.session.completed` / `checkout.session.expired` /
   `checkout.session.async_payment_succeeded` / `checkout.session.async_payment_failed`
3. 領収書（適格請求書）を発行する場合は Stripe 側で登録番号・請求書設定を行う

### ロール
- **Seminar Manager**: セミナー・申込・設定の管理
- **Seminar Staff**: 閲覧と当日チェックイン
- 社内 MTG は全デスクユーザーが作成可。閲覧は主催者・参加者（と Manager）のみ

## テスト

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app lifegence_seminar
```

外部 API（Zoom / Stripe）はテストでモックする。

## セキュリティ
ゲスト到達エンドポイントの認可・入力検証・レート制限は
[docs/security/guest-endpoint-audit.md](docs/security/guest-endpoint-audit.md) を参照。
