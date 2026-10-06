# ウェブサイトのデザイン手順書

EventMeet ─ 公開ページの見た目とレイアウトを変える

対象: EventMeet 0.2.0 以降（Frappe v15 / v16）。読者: Frappe システム管理者、Web デザイナー、開発者。

[English](../en/website-design.md)

## 1. 概要

公開ページは、`/seminars`（一覧）、各セミナーのページ、申込内容のページ（`/seminar-registration`）、
アンケート（`/seminar-feedback`）です。変えたい範囲に応じて、次の 3 段階から選びます。

| 段階 | 変えられるもの | 設定する場所 | 必要な知識 |
|---|---|---|---|
| 1. Frappe のウェブサイト設定 | サイト全体のロゴ、メニュー、フッター、色、フォント、トップページ | ウェブサイト設定、ウェブサイトテーマ（Frappe 標準） | 不要 |
| 2. EventMeet のデザイン設定 | 標準デザインの選択、デザイントークン（色・角丸・幅・列数）、追加の CSS、公開ページの上下に出すヘッダー・フッター | セミナー設定 →「ウェブサイトのデザイン」 | CSS（任意） |
| 3. テンプレートの差し替え | 各ページのレイアウトと HTML | 自社用の小さな Frappe アプリ | HTML / Jinja、アプリのデプロイ |

段階は組み合わせて使えます。たとえば、標準デザインのトークンを少し変え、ロゴはウェブサイト設定で入れる、といった使い方です。

## 2. Frappe のウェブサイト設定（段階 1）

Frappe 標準の設定です。開発は不要で、System Manager が設定できます。

| やりたいこと | 設定する場所 |
|---|---|
| サイトのトップ（`/`）をセミナー一覧にする | ウェブサイト設定 →「ホーム」→「ホームページ」に `seminars` |
| ロゴ、ファビコン | ウェブサイト設定 →「ナビゲーションバー」→「ブランド画像」または「ブランドHTML」、「ファビコン」 |
| 上部メニューのリンク、「ログイン」リンクを隠す | ウェブサイト設定 →「ナビゲーションバー」→「トップバーアイテム」、「ログインを非表示」 |
| フッター（リンク、住所、著作権表示） | ウェブサイト設定 →「フッター」 |
| meta タグ、OGP、Web フォントの読み込み | ウェブサイト設定 →「&lt;head&gt; HTML」 |
| サイト全体の色、Google フォント、ボタンの形、SCSS | ウェブサイトテーマ（作成してから、ウェブサイト設定で選択） |

これらはログイン画面を含むサイト全体に適用されます。

## 3. EventMeet のデザイン設定（段階 2）

> **画面:** **Frappe**（`https://<サイト>/app/seminar-settings`）の「ウェブサイトのデザイン」欄。System Manager または Seminar Manager。

### 3.1 標準デザイン

| デザイン | 見た目 |
|---|---|
| 標準 | 既定。落ち着いた見た目で、サイトのテーマの色に合わせる |
| コーポレート | 紺色、角の丸みなし、タイトルに色帯、ページ幅広め |
| フレンドリー | 暖色、角丸のカードを 2 列に並べ、画像を上に表示 |
| ミニマル | 枠なし、大きなタイトル、細い区切り線 |

| 標準 | コーポレート |
|---|---|
| ![標準](../images/website-design/design-standard.png) | ![コーポレート](../images/website-design/design-corporate.png) |
| **フレンドリー** | **ミニマル** |
| ![フレンドリー](../images/website-design/design-friendly.png) | ![ミニマル](../images/website-design/design-minimal.png) |

スクリーンショットは英語表示の画面です。日本語で表示している場合、見出しなどは日本語になります。

### 3.2 カスタム CSS とデザイントークン

「カスタム CSS」はデザインの後に読み込まれるので、デザイントークン（CSS 変数）や、任意のスタイルを変更できます。
公開ページ全体は `.em-page` で囲まれていて、`em-design-<デザイン>`（例：`em-design-friendly`）のクラスが付いています。

```css
/* ブランドカラー、角丸を小さく、広い画面では 3 列 */
.em-page { --em-primary: #0f766e; --em-radius: 4px; --em-list-columns: 3; --em-card-direction: column; --em-card-image-width: 100%; }
```

| トークン | 既定値（標準） | 用途 |
|---|---|---|
| `--em-primary` | テーマのプライマリカラー | ボタン（標準以外のデザイン）、アクセント |
| `--em-on-primary` | `#fff` | ボタンの文字色 |
| `--em-text` | 継承 | 文字色 |
| `--em-muted` | `#6b7280` | 補足の文字 |
| `--em-border` / `--em-border-strong` | `#e5e7eb` / `#9ca3af` | 枠線 / マウスを重ねたときとバッジの枠線 |
| `--em-surface` | 透明 | カードと囲みの背景 |
| `--em-page-bg` | 透明 | セミナー部分の背景 |
| `--em-radius` / `--em-badge-radius` | `8px` / `999px` | カード・囲みの角丸 / バッジの角丸 |
| `--em-max-width` | `880px` | 本文の幅 |
| `--em-title-size` / `--em-title-weight` | `1.8rem` / `700` | ページタイトル |
| `--em-heading-size` | `1.2rem` | カードのタイトルと見出し |
| `--em-list-columns` | `1` | 一覧の列数（スマートフォンでは常に 1） |
| `--em-card-direction` | `row` | `row`：画像を横に、`column`：画像を上に |
| `--em-card-image-width` / `--em-card-image-height` | `200px` / `112px` | カードの画像の大きさ |
| `--em-shadow` | なし | カードと囲みの影 |

ページ内のクラス名（`ls-card`、`ls-title`、`ls-box` など）にもスタイルを当てられますが、版によって変わることがあります。できるだけトークンを使ってください。

### 3.3 ヘッダー HTML とフッター HTML

「ヘッダー HTML」と「フッター HTML」は、公開ページの上と下に表示されます。お知らせ（「早割は 10 月 31 日まで」など）や規約へのリンクに使えます。
HTML は無害化され、`<script>` 要素とイベント属性（`onclick` など）は削除されます。テンプレートとしても実行されません。

### 3.4 例：カスタム CSS とヘッダー・フッター

[`examples/website-design`](../../examples/website-design) に、標準デザインにそのまま貼り付けられるサンプルがあります。
`custom.css`（ティールのブランドカラー、淡い背景に白いカード、画像が上のカードを 3 列。タブレットでは 2 列、スマートフォンでは 1 列）、
`header.html`（早割の告知と紹介文）、`footer.html`（主催者、問い合わせ先、規約へのリンク）の 3 つです。会社名は架空のものです。

| 広い画面 | スマートフォン |
|---|---|
| ![カスタム CSS とヘッダー・フッター](../images/website-design/custom-list.png) | ![スマートフォン](../images/website-design/custom-mobile.png) |

注意点が 2 つあります。

- カスタム CSS は、スマートフォン向けの設定も含めた標準のスタイルの後に読み込まれます。`--em-list-columns` やカードの並びを変えるときは、サンプルのように、小さい画面向けのメディアクエリも自分で書いてください。
- ヘッダーとフッターの HTML では `class` 属性と `style` 属性を使えます。クラスの見た目はカスタム CSS で指定します。保存した HTML は無害化されます（Frappe v15 では、`<script>` は保存時にただの文字に置き換わり、実行されません）。

## 4. テンプレートの差し替え（段階 3）

レイアウトや HTML を変えるには、自社用のアプリからページのテンプレートを差し替えます。EventMeet は各ページのテンプレートを
フック `eventmeet_website_templates` で探し、同じキーを設定したアプリが複数あれば、最後にインストールしたアプリが優先されます。

```python
# 自社アプリの hooks.py
eventmeet_website_templates = {
	"seminar_list": "my_theme/templates/eventmeet/seminar_list.html",
	"seminar_detail": "my_theme/templates/eventmeet/seminar_detail.html",
}
```

差し替えるテンプレートは EventMeet のテンプレートを継承し、必要なブロックだけを上書きします。上書きしていない部分は、EventMeet を更新するとその変更がそのまま反映されます。

```jinja
{% extends "eventmeet/templates/eventmeet/seminar_list.html" %}
{% block em_list_header %}<h1>開催予定のイベント</h1>{% endblock %}
```

`{{ self.<ブロック名>() }}` で、ブロックを別の場所に表示することもできます。デモアプリでは、これで申込欄を右側に移しています。

### 4.1 テンプレートとブロック

| キー | ページ | EventMeet のテンプレート | ブロック |
|---|---|---|---|
| `seminar_list` | `/seminars` | `eventmeet/templates/eventmeet/seminar_list.html` | `em_list_header`、`em_card`（カード 1 枚分。変数 `s`）、`em_empty` |
| `seminar_detail` | セミナーのページ | `eventmeet/templates/eventmeet/seminar_detail.html` | `em_hero`、`em_overview`、`em_description`、`em_program`、`em_speakers`、`em_registration` |
| `registration` | `/seminar-registration` | `eventmeet/templates/eventmeet/registration.html` | `em_not_found`、`em_title`、`em_status`、`em_details`、`em_join`、`em_checkin_qr`、`em_survey` |
| `feedback` | `/seminar-feedback` | `eventmeet/templates/eventmeet/feedback.html` | `em_title`、`em_form` |

どのテンプレートも `eventmeet/templates/eventmeet/layout.html` を継承しています。layout には `em_styles`（デザインの CSS。`{{ super() }}` で残したまま自分の CSS を追加できます）、`em_header`、`em_content`、`em_footer` のブロックがあります。
各ページで使える変数は、それぞれのテンプレートの先頭に書いてあります。

> [!WARNING]
> セミナーのページとアンケートは、決まった要素 ID を探すスクリプトでフォームを送信します。
> `em_registration` や `em_form` を上書きするときは、`seminar_detail.html` と `feedback.html` の先頭に書いてある
> フォームの ID と項目名（例：`ls-register-form`、`ls-register-message`、項目 `ticket_type`、`attendee_name`、`email`、`company`、`phone`、非表示の `website`）を残してください。

### 4.2 デモアプリ

[`examples/eventmeet_theme_example`](../../examples/eventmeet_theme_example) は、そのままインストールできるアプリです。
2 つのテンプレートを差し替えます。一覧は大きな見出しと日付のタイルを使ったランディングページ風、セミナーのページは申込欄を右側に固定した 2 段組みです。

| 一覧 | セミナーのページ |
|---|---|
| ![デモの一覧](../images/website-design/template-example-list.png) | ![デモのセミナーのページ](../images/website-design/template-example-detail.png) |

1. フォルダをコピーし、アプリの名前を変えます（フォルダ名、パッケージ名、`hooks.py` の `app_name`、`pyproject.toml`）。
2. `<アプリ>/templates/eventmeet/` のテンプレートを自社のデザインに変更します。
3. アプリを Git リポジトリに置き、ベンチにインストールします。

   ```bash
   bench get-app <リポジトリの URL>
   bench --site <site> install-app <アプリ名>
   ```

アプリをアンインストールすると、EventMeet 標準のテンプレートに戻ります。

### 4.3 テンプレートをブラウザで編集できない理由

Jinja のテンプレートはサーバー上で実行されます。ブラウザからテンプレートを編集できると、その設定を触れる人がサーバー上で任意の処理を動かせてしまいます。
そのため EventMeet は、インストールされたアプリに含まれるテンプレート（ほかのコードと同じくレビューしてデプロイされるもの）だけを使います。
段階 2 の設定が、CSS と無害化した HTML だけなのも同じ理由です。
