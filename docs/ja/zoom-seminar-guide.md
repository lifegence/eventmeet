# Zoom セミナー設定・運用手順書

EventMeet ─ Zoom によるオンライン / ハイブリッドセミナーの管理

対象: EventMeet 0.1.0 以降（Frappe v15 / v16）。読者: Zoom アカウントの管理者、Frappe システム管理者、セミナー担当者（Seminar Manager）。

[English](../en/zoom-seminar-guide.md)

> [!IMPORTANT]
> 本書の手順は、EventMeet のプログラムの内容をもとに作成したもので、**実際の Zoom アカウントではまだ検証していません**。
>
> 初回は本番のセミナーで使う前に、6 章の「初回の検証手順」に沿って検証用のセミナーで確認し、結果欄に記入してください。Zoom の画面の名称や配置は Zoom の更新で変わることがあります。本書と画面が異なる場合は、GitHub の Issue でお知らせください。

## 1. 概要

### 1.1 目的

本書は、EventMeet のセミナーを Zoom で開催するために必要な Zoom と Frappe の設定、およびセミナーの作成から終了後の出席確認までの運用手順をまとめたものです。社内ミーティングの Google Meet 連携は、[Google Workspace 設定手順書](google-meet-setup.md) を参照してください。

### 1.2 連携の仕組み

- Frappe は Zoom の **Server-to-Server OAuth アプリ**を使って Zoom API を呼び出します。Zoom アカウント単位の認証のため、ホストごとの個別の承認は不要です。
- セミナーのステータスを「受付中」にして保存すると、Zoom に**登録制のミーティング**（またはウェビナー）が自動で作成されます。ホストは「Zoom ホストアカウント」に登録したライセンスの中から、その時間に空いているものが自動で割り当てられます。
- 申込が確定すると、申込者を Zoom の登録者として登録し、**申込者ごとの個別参加 URL** を申込確認メールで送ります（Zoom からはメールを送りません）。開始前のリマインドメールにも同じ URL が入ります。
- セミナーのタイトル・日時を変更すると Zoom 側も更新され、ステータスを「中止」にすると Zoom 側のミーティングが削除されます。
- セミナーの終了後、Zoom の参加者レポートから参加者と視聴時間を取り込み、申込ごとに「オンライン出席」「オンライン視聴時間（分）」を記録します。
- Zoom の Webhook で終了の通知を受け取ります（推奨。未設定でも、予定終了時刻をもとに出席の取り込みは行われます）。

### 1.3 必要な Zoom の契約

| 項目 | 内容 |
|---|---|
| ホスト用ライセンス | 有料ライセンス（Pro 以上）が付与された Zoom ユーザー。1 ライセンスで同時に開催できるのは 1 件のため、**必要なライセンス数は同時開催数のピーク**です（社員数ではありません） |
| ウェビナー | ウェビナー形式を使う場合は、ホストユーザーに Zoom Webinars のアドオン（参加者上限付き）を割り当てます。通常の登録制ミーティングだけなら不要です |
| 参加者レポート | 出席・視聴時間の取り込みに Zoom のレポート機能を使います（Pro 以上） |
| アプリの作成権限 | Server-to-Server OAuth アプリを作成するユーザーに、Zoom の管理者がロールで作成権限を付与しておく必要があります |

### 1.4 作業する画面と担当

| 手順 | 作業する画面 | 担当 |
|---|---|---|
| 3.1〜3.5 アプリの作成・スコープ・Webhook・有効化 | **Zoom App Marketplace**（`https://marketplace.zoom.us/`） | Zoom アカウントのオーナーまたは管理者 |
| 3.6 ホストユーザーとライセンス | **Zoom ウェブポータル**（`https://zoom.us/`）の「ユーザー管理」 | Zoom アカウントのオーナーまたは管理者 |
| 4 章 EventMeet の設定 | **Frappe**（`https://<サイト>/app/...`） | System Manager または Seminar Manager |
| 5 章 セミナーの運用 | **Frappe** | Seminar Manager（当日の受付は Seminar Staff も可） |

### 1.5 Frappe のロール

| ロール | できること |
|---|---|
| System Manager / Seminar Manager | オンライン会議設定・Zoom ホストアカウント・セミナー設定の変更、セミナーの作成・変更、申込の管理、ホストとして開始、参加ログの取得 |
| Seminar Staff | セミナーの閲覧、申込の閲覧・更新、当日の QR 受付 |
| その他のユーザー | セミナー関連の画面は使えません |

## 2. 事前確認チェックリスト

| 確認 | 項目 |
|---|---|
| □ | Zoom アカウントのオーナーまたは管理者のアカウントを利用できる |
| □ | ホストにする有料ライセンスのユーザー（例: seminar-host01@example.com）を用意できる。ウェビナーを使う場合は Webinars アドオンも用意できる |
| □ | Frappe に System Manager または Seminar Manager でログインできる |
| □ | Frappe サイトがインターネットから HTTPS で到達できる（Webhook に必要。例: `https://erp.example.com`） |
| □ | 有料チケットを販売する場合は、Stripe の設定が済んでいる（[README](../../README_ja.md#stripe) を参照。本書の対象外） |

## 3. Zoom の設定

### 3.1 Server-to-Server OAuth アプリを作成する

> **画面:** Zoom App Marketplace（`https://marketplace.zoom.us/`）

1. Zoom App Marketplace に、Zoom アカウントの管理者でサインインします。
2. 右上の「Develop」→「Build App」を選びます。
3. アプリの種類で「Server to Server OAuth App」を選び、作成します。アプリ名は例: `EventMeet` とします。
4. 「Information」の画面で、会社名と開発者の連絡先（名前・メールアドレス）を入力します。

> [!NOTE]
> 「Server to Server OAuth App」が選べない場合は、Zoom の管理者が「ユーザー管理」→「ロール」で、そのユーザーのロールに Server-to-Server OAuth アプリの表示・編集の権限を付けてください。

### 3.2 認証情報を控える

> **画面:** Zoom App Marketplace（作成したアプリの「App Credentials」）

1. 「App Credentials」の画面に表示される **Account ID**、**Client ID**、**Client Secret** を控えます。4.1 で Frappe に登録します。

> [!WARNING]
> Client Secret は、Zoom アカウントのミーティングを操作できる秘密の情報です。メールやチャットに貼り付けず、Frappe への登録が終わったら控えたメモは削除してください。

### 3.3 スコープを追加する

> **画面:** Zoom App Marketplace（作成したアプリの「Scopes」）

1. 「Scopes」の画面で「Add Scopes」を押します。
2. 次の表のスコープを検索して、すべて追加します（付録 A にコピー用の一覧があります）。

| スコープ | 用途 |
|---|---|
| `meeting:write:meeting:admin` | ミーティングの作成 |
| `meeting:update:meeting:admin` | ミーティングの変更 |
| `meeting:delete:meeting:admin` | ミーティングの削除 |
| `meeting:read:meeting:admin` | ミーティングの参照（ホスト開始 URL） |
| `meeting:write:registrant:admin` | 登録者の追加 |
| `meeting:update:registrant_status:admin` | 登録者の取消 |
| `webinar:write:webinar:admin` | ウェビナーの作成 |
| `webinar:update:webinar:admin` | ウェビナーの変更 |
| `webinar:delete:webinar:admin` | ウェビナーの削除 |
| `webinar:read:webinar:admin` | ウェビナーの参照（ホスト開始 URL） |
| `webinar:write:registrant:admin` | ウェビナー登録者の追加 |
| `webinar:update:registrant_status:admin` | ウェビナー登録者の取消 |
| `report:read:list_meeting_participants:admin` | ミーティング参加者レポート（出席・視聴時間） |
| `report:read:list_webinar_participants:admin` | ウェビナー参加者レポート（出席・視聴時間） |
| `meeting:read:summary:admin` | AI Companion 会議要約（社内ミーティング用。任意） |

> [!NOTE]
> ウェビナーを使わない場合でも、`webinar:` のスコープは追加しておくことをおすすめします（後からウェビナーを使うときにアプリの設定を変えずに済みます）。

### 3.4 Webhook（Event Subscription）を設定する

> **画面:** Zoom App Marketplace（作成したアプリの「Feature」）

セミナーの終了を Zoom から通知してもらうための設定です。手順の途中で Frappe 側の設定（4.1）を先に行う必要があります。

1. 「Feature」の画面で「Event Subscriptions」をオンにし、「Add Event Subscription」を押します。
2. サブスクリプション名（例: `EventMeet`）を入力します。
3. 画面に表示される **Secret Token** を控えます。
4. **ここで 4.1 に進み、Frappe の「Webhook Secret Token」に控えた Secret Token を登録して保存します。**（Frappe は Secret Token を使って Zoom からの確認要求に応答するため、先に登録しておかないと次の検証が失敗します。）
5. Zoom の画面に戻り、「Event notification endpoint URL」に次の URL を入力して「Validate」を押します。`<サイト>` は Frappe サイトのホスト名に置き換えます（例: `erp.example.com`）。

```
https://<サイト>/api/method/eventmeet.api.webhooks.zoom
```

6. 「Add Events」で次のイベントを追加し、保存します。

| イベント（表示名の例） | イベント名 | 用途 | 要否 |
|---|---|---|---|
| End Meeting | `meeting.ended` | ミーティング形式のセミナー・社内ミーティングの終了 | 推奨 |
| End Webinar | `webinar.ended` | ウェビナー形式のセミナーの終了 | ウェビナーを使う場合 |
| Meeting summary completed | `meeting.summary_completed` | 社内ミーティングの AI Companion 要約の取り込み（セミナーでは使いません） | 任意 |

> [!NOTE]
> イベントの表示名は Zoom の画面で変わることがあります。検索欄にイベント名（`meeting.ended` など）の一部を入れて探してください。

### 3.5 アプリを有効化する

> **画面:** Zoom App Marketplace（作成したアプリの「Activation」）

1. 「Activation」の画面で「Activate your app」を押し、アプリを有効にします。有効化していないと、Frappe からの認証が失敗します。

### 3.6 ホストユーザーとライセンスを準備する

> **画面:** Zoom ウェブポータル（`https://zoom.us/`）→「ユーザー管理」→「ユーザー」

1. セミナーのホストにするユーザーに、有料ライセンス（Pro 以上）が付与されていることを確認します。セミナー専用のユーザー（例: seminar-host01@example.com）を用意すると、担当者の異動の影響を受けません。
2. ウェビナーを使う場合は、そのユーザーに Webinars のアドオンを割り当て、参加者上限（例: 500）を控えます。
3. 各ユーザーのミーティングの参加者上限（例: Pro は 100 名、大規模ミーティングのアドオンがあればその人数）を控えます。4.2 で入力します。
4. 自動録画をクラウドに保存する場合は、クラウド記録が使えるライセンスか確認します。

## 4. Frappe（EventMeet）の設定

### 4.1 オンライン会議設定

> **画面:** Frappe（`https://<サイト>/app/conferencing-settings`）

1. Frappe に System Manager（または Seminar Manager）でログインし、「オンライン会議設定」を開きます。
2. 「Zoom」の欄で次の項目を設定し、保存します。

| 欄 | 項目（画面の表示） | 設定値 |
|---|---|---|
| Zoom | Zoom を有効化 | オン |
| Zoom | アカウント ID | 3.2 で控えた Account ID |
| Zoom | クライアントID | 3.2 で控えた Client ID |
| Zoom | クライアントシークレット | 3.2 で控えた Client Secret |
| Zoom | Webhook Secret Token | 3.4 で控えた Secret Token |
| Zoom | 自動録画 | 録画しない／ローカル（ホストの PC）／クラウド（Zoom クラウド） |
| Zoom | 社内ミーティングで待機室を使用 | 社内ミーティングを Zoom で開く場合の設定（セミナーには影響しません） |
| Zoom ホスト割当 | セッション間の余裕時間（分） | 同じホストの会議の前後に空ける時間（例: 15） |
| Zoom ホスト割当 | 参加ログ取得までの待ち時間（分） | 予定終了時刻から出席の取り込みを始めるまでの時間（既定 15） |

> [!NOTE]
> セミナーは常に Zoom を使います。「既定」欄の「社内ミーティングの会議ツール」は社内ミーティング用の設定のため、Google Meet のままで構いません。
>
> クライアントシークレットと Webhook Secret Token は暗号化して保存され、画面には「*****」と表示されます。

### 4.2 Zoom ホストアカウントを登録する

> **画面:** Frappe（`https://<サイト>/app/zoom-host-account/new`）

3.6 で準備したホストユーザーを 1 人ずつ登録します。同時に開催したいセミナーの数だけ登録が必要です。

| 項目（画面の表示） | 設定値 |
|---|---|
| ラベル | わかりやすい名前（例: セミナー用ホスト 1） |
| Zoom ユーザー | ホストユーザーのメールアドレス（または Zoom のユーザー ID） |
| 有効 | オン |
| ライセンス | Pro / Business / Business Plus / Enterprise から選択 |
| ミーティング上限人数 | このユーザーのミーティングの参加者上限（例: 100） |
| ウェビナー上限人数 | Webinars アドオンの参加者上限。アドオンがなければ 0 |
| セミナーに使用 | オン |
| 社内ミーティングに使用 | 社内ミーティングに Zoom を使わない場合はオフ |

> [!NOTE]
> 割り当ては、セミナーの「定員」以上の上限人数を持つホストのうち、上限人数が最も小さいものから選ばれます（大きなライセンスを大規模なセミナーのために残すため）。定員が 0（無制限）の場合は 1 名として扱います。

### 4.3 セミナー設定（メール）

> **画面:** Frappe（`https://<サイト>/app/seminar-settings`）

| 項目（画面の表示） | 設定値 |
|---|---|
| リマインド送信（開始の何時間前） | 個別参加 URL 入りのリマインドメールを送る時間（例: 24） |
| 終了後にアンケート依頼を送信 | アンケートを使う場合はオン |

Frappe サイトから申込者にメールを送るため、Frappe の送信用メールアカウントが設定されている必要があります。

## 5. セミナーの運用手順

### 5.1 セミナーを作成する（下書き）

> **画面:** Frappe（「セミナー」→「新規」）

1. 「実施概要」タブで、タイトル、形式、主催者、開始日時、終了日時、申込締切日時（空欄なら開始日時）、定員を入力します。形式は、オンラインのみなら「オンライン」、会場とオンラインの両方なら「ハイブリッド」を選びます（ハイブリッドは会場の指定が必要です）。
2. 概要・説明・バナー画像・プログラムを入力します。概要はセミナー一覧に表示されます。
3. 「チケット」タブでチケット種別を 1 つ以上追加します（無料なら価格 0）。
4. 「オンライン」タブで「会議の種類」を選びます。「会議」は登録制の Zoom ミーティング、「ウェビナー」は Zoom ウェビナー（Webinars アドオンが必要）です。
5. 「ウェブサイト」タブで「公開済」をオンにします。
6. ステータスは「下書き」のまま保存します。この時点では Zoom にはまだ何も作られません。

> [!WARNING]
> 定員がホストの上限人数を超えていると、次の 5.2 で「利用可能な Zoom ホストがありません」となります。定員を見直すか、上限人数の大きいホストを登録してください。

### 5.2 申込の受付を開始する

1. ステータスを「**受付中**」にして保存します。
2. 保存すると Zoom のミーティング（またはウェビナー）が自動で作成され、「オンライン」タブに「オンライン会議」と「参加 URL（共通）」が入ります。
3. 「Web サイトで表示」を押し、公開ページ（`/seminars`）にセミナーが表示されることを確認します。

> [!WARNING]
> 「参加 URL（共通）」は Zoom の登録ページの URL です。申込者には個別参加 URL が自動で届くため、共通の URL は配布しないでください（共通の URL から Zoom で直接登録した人は、EventMeet の申込として記録されず、出席も取り込まれません）。

### 5.3 申込と個別参加 URL

- 申込者は公開ページ（`https://<サイト>/seminars`）から申し込みます。無料チケットはその場で確定し、有料チケットは Stripe の決済完了後に確定します。
- 確定すると、申込者が Zoom に登録され、個別参加 URL が申込確認メールで届きます。申込の「個別参加 URL」欄にも記録されます。
- Zoom への登録に一時的に失敗した場合は、10 分ごとに自動で再試行し、登録できた時点で確認メールを送ります。
- 申込の一覧は、セミナーの画面の「申込一覧」ボタンで開けます。

### 5.4 当日の運営

- 開始の数分前に、Seminar Manager がセミナーの画面で「Zoom」→「**ホストとして開始**」を押すと、割り当てられたホストとして Zoom が開きます。このリンクはホストの全権限を持つため、共有しないでください。
- 参加者は、メールで届いた個別参加 URL から参加します。
- ハイブリッドの場合、会場の受付は Seminar Staff が `/seminar-checkin` で QR コードを読み取って行います。

### 5.5 終了後の出席確認

1. 予定終了時刻から 15 分（「参加ログ取得までの待ち時間」）たつと、出席の取り込みが自動で始まります。取り込みは 10 分ごとに実行され、Zoom のレポートができていなければ最大 12 回まで再試行します。
2. すぐに確認したい場合は、セミナーの画面で「Zoom」→「**参加ログを取得**」を押します。
3. 各申込の「オンライン出席」と「オンライン視聴時間（分）」を確認します。照合はメールアドレスで行うため、個別参加 URL から参加した人が対象です。
4. 確認が終わったら、セミナーのステータスを「終了」にして保存します。

> [!NOTE]
> Zoom の AI Companion の会議要約の取り込みは、社内ミーティングだけの機能です。セミナーでは取り込みません。

### 5.6 変更・中止

- **日時・タイトルの変更**：セミナーを変更して保存すると、Zoom 側も自動で更新されます。個別参加 URL は変わりません。申込者への変更の連絡は、必要に応じて別途行ってください（Zoom からは通知されません）。
- **中止**：ステータスを「中止」にして保存すると、Zoom 側のミーティングが削除されます。申込者への連絡と、有料チケットの返金は申込ごとに行ってください。
- **申込の取消**：申込を取り消すと、Zoom の登録も取り消され、個別参加 URL は使えなくなります。

## 6. 初回の検証手順

本書は未検証のため、初回は検証用のセミナー（無料チケット、定員は少なめ、公開はテスト後に戻す）で次の順に確認し、結果欄に記入してください。

| No. | 操作 | 期待する結果 | 結果 |
|---|---|---|---|
| 1 | 4.1 の設定を保存した後、3.4 で「Validate」を押す | Zoom の画面で検証が成功する |  |
| 2 | 形式「オンライン」、会議の種類「会議」、無料チケット 1 件、公開済でセミナーを作成し、ステータス「下書き」で保存する | 保存できる。Zoom にはまだ作られない |  |
| 3 | ステータスを「受付中」にして保存する | 「オンライン会議」と「参加 URL（共通）」が入る。ホストの Zoom アカウントに登録制ミーティングが作成されている（Zoom のウェブポータルで確認） |  |
| 4 | `/seminars` から自分のメールアドレスで申し込む | 申込が「確認済」になり、個別参加 URL 入りの確認メールが届く。Zoom のミーティングの登録者に追加されている |  |
| 5 | セミナーの開始日時を変更して保存する | Zoom のミーティングの日時も変わる |  |
| 6 | 「Zoom」→「ホストとして開始」を押す | ホストとして Zoom が開く |  |
| 7 | 別の端末から個別参加 URL で参加し、数分後に退出してミーティングを終了する | Webhook を設定していれば、Frappe の「オンライン会議」のステータスが「終了」になる |  |
| 8 | 予定終了時刻の 15 分後以降に確認する（またはすぐに「参加ログを取得」を押す） | 申込の「オンライン出席」がオンになり、「オンライン視聴時間（分）」が入る |  |
| 9 | （ウェビナーを使う場合）会議の種類「ウェビナー」で 2〜8 を繰り返す | 同じ結果になる |  |
| 10 | 別の検証用セミナーをステータス「受付中」にした後、「中止」にして保存する | Zoom のミーティングが削除される |  |

> [!NOTE]
> 検証が終わったら、検証用のセミナーを非公開にし、ステータスを「中止」にしてください。

## 7. トラブルシューティング

エラーの詳細は、Frappe の「エラーログ」一覧で確認できます。

| 症状・エラー | 主な原因 | 対処 |
|---|---|---|
| 「Zoom authentication failed (400/401)」 | Account ID / Client ID / Client Secret の誤り、アプリが有効化されていない | 3.2 の値を貼り直す。3.5 でアプリを有効化する |
| 「Zoom API … failed (400)」または (403) でスコープ不足の内容 | 必要なスコープが追加されていない | 3.3 のスコープをすべて追加する。追加後はアプリの再有効化が必要な場合がある |
| 「Zoom is not enabled in Conferencing Settings」 | オンライン会議設定で Zoom が無効 | 4.1 で「Zoom を有効化」をオンにする |
| 「{N} 名の会議を開催できる有効な Zoom ホストアカウントがありません」 | 定員以上の上限人数を持つ、セミナーに使用するホストがない | 定員を見直すか、4.2 でホストを追加・修正する（ウェビナーは「ウェビナー上限人数」を確認） |
| 「… はすべての Zoom ホストアカウントが使用中です」 | 同じ時間帯（前後の余裕時間を含む）にすべてのホストが使われている | ホストを追加するか、時間を変更する |
| 申込ページで「オンライン会議の準備ができていません」 | ステータスを「受付中」にしたときに Zoom の作成が失敗した | エラーログを確認して原因を直し、セミナーを再度保存する |
| 確認メールに個別参加 URL が入っていない | Zoom への登録が一時的に失敗した | 10 分ごとの自動再試行を待つ。続く場合はエラーログを確認する |
| Zoom の「Validate」が失敗する | Frappe に Secret Token が未登録、または値が違う。サイトにインターネットから届かない | 4.1 で Webhook Secret Token を保存してから再度押す。URL が HTTPS で開けるか確認する |
| 出席が取り込まれない | Zoom のレポート作成待ち、参加者が共通 URL や別のメールアドレスで参加した、レポートのスコープ不足 | 時間をおいて「参加ログを取得」を押す。個別参加 URL から参加してもらう。3.3 の `report:` スコープを確認する |

## 8. セキュリティと運用

- **秘密情報の管理**：Client Secret と Secret Token は Frappe にだけ保存し、控えたメモは削除します。漏えいの疑いがあるときは Zoom App Marketplace で再発行し、Frappe の設定を更新します。
- **ホストとして開始のリンク**：ホストの全権限を持つため、Seminar Manager 以外に共有しません。
- **ライセンスの見直し**：必要なライセンス数は同時開催数のピークです。開催予定に合わせてホストアカウントの数を見直します。
- **録画**：クラウド録画を使う場合は、保存期間と公開範囲を Zoom 側で設定します。
- **参加者の個人情報**：申込情報と出席の記録は、セミナー運営の目的に限って使います。

## 付録 A　スコープ一覧（コピー用）

```
meeting:write:meeting:admin
meeting:update:meeting:admin
meeting:delete:meeting:admin
meeting:read:meeting:admin
meeting:write:registrant:admin
meeting:update:registrant_status:admin
webinar:write:webinar:admin
webinar:update:webinar:admin
webinar:delete:webinar:admin
webinar:read:webinar:admin
webinar:write:registrant:admin
webinar:update:registrant_status:admin
report:read:list_meeting_participants:admin
report:read:list_webinar_participants:admin
meeting:read:summary:admin
```

## 付録 B　参考資料

| 資料 | URL |
|---|---|
| Server-to-Server OAuth アプリの作成（Zoom Developer） | https://developers.zoom.us/docs/internal-apps/s2s-oauth/ |
| Webhook の使い方とエンドポイントの検証（Zoom Developer） | https://developers.zoom.us/docs/api/webhooks/ |
| EventMeet README（Zoom / Stripe のセットアップ概要） | [README_ja.md](../../README_ja.md) |
