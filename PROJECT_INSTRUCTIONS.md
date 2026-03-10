# たまのためいき。システム 指示書
最終更新: 2026/03/11

## プロジェクト概要
詩・BGM・映像を自動生成してYouTube・Instagram・X・TikTokに毎日自動投稿するシステム。

## リポジトリ
- GitHub: https://github.com/tamanotameiki-art/tameiki
- ローカル: E:\tamanotameiki_system\tameiki_code\tameiki_system

## 各種ID・キー
- MetaアプリID: 2067395174122332
- InstagramアプリID: 930026266391655
- Metaシステムユーザー「tameiki-bot」ID: 6158391839902
- InstagramユーザーID: 26043667661961320
- YouTubeチャンネルID: UCE8QDag3lHM80xIyEGe9_5w
- Facebookページ名: Tmik-api-System（API連携用・非公開相当）

## GitHub Secrets登録済み
- INSTAGRAM_ACCESS_TOKEN（IGAAトークン・毎月1日自動リフレッシュ）
- INSTAGRAM_APP_SECRET
- YOUTUBE_API_KEY（Google Cloud「tameiki-system」プロジェクトのAPIキー）
- YOUTUBE_CREDENTIALS（OAuth2・動画アップロード用）
- GOOGLE_CREDENTIALS（サービスアカウント・スプレッドシート用）
- SPREADSHEET_ID
- GH_TOKEN
- GH_REPO
- X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET / X_BEARER_TOKEN
- OPENWEATHER_API_KEY
- PINTEREST_ACCESS_TOKEN / PINTEREST_APP_ID
- CLAUDE_API_KEY

## スプレッドシート「投稿履歴」シートのヘッダー
投稿日時 / 詩 / 背景ファイル名 / フィルター / BGMタイトル / 環境音1 / 環境音2 / 環境音3 /
X投稿ID / YouTube投稿ID / Instagram投稿ID / TikTok投稿ID /
X再生数 / YouTube再生数 / Instagram再生数 / TikTok再生数 /
X保存数 / YouTube保存数 / Instagram保存数 /
週間ベスト / 月間ベスト /
YouTubeいいね数 / YouTubeコメント数 / Instagramいいね数 / Instagramコメント数 / Instagramインプレッション / 収集日時

## GitHub Actionsワークフロー一覧
- daily_post.yml: 毎日21:00 JST自動投稿（YouTube・Instagram・X・TikTok）
- collect_analytics.yml: 毎日8:00 JSTにYouTube・Instagram反応数収集（YOUTUBE_API_KEY使用）
- refresh_instagram_token.yml: 毎月1日にInstagramトークン自動リフレッシュ
- bgm_mastering.yml: BGMマスタリング

## スクリプト一覧（scripts/）
- post_youtube.py: YouTube Shorts投稿（OAuth2）
- post_instagram.py: Instagram投稿（400エラー未解決）
- post_x.py: X投稿
- post_pinterest.py: Pinterest投稿（Standard申請待ち）
- prepare_tiktok.py: TikTok投稿準備（storageQuotaExceededエラー未解決）
- collect_analytics.py: YouTube・Instagram反応数収集（直近30本・YOUTUBE_API_KEY使用）
- generate_captions.py: キャプション生成
- generate_images.py: 画像生成
- run_generate.py: メイン生成スクリプト（poem_wrappedの出力確認が必要→下記注意事項参照）
- bgm_mastering.py: BGMマスタリング

## 完了済みタスク
- Instagramプロアカウント設定・Facebookページ連携
- Meta for Developers「tameiki-system」アプリ設定・テスター登録
- システムユーザー「tameiki-bot」作成・権限付与
- Instagramトークン毎月自動リフレッシュ（refresh_instagram_token.yml）動作確認済み
- collect_analytics.py作成・動作確認完了
- スプレッドシート投稿履歴シートに反応数列を自動追加
- daily_post.ymlの重複アナリティクスジョブを削除・整理済み

## 注意事項・要確認項目

### run_generate.py — poem_wrappedの出力確認
daily_post.ymlはsteps.generate.outputs.poem_wrappedを参照している。
run_generate.pyのmain()内に以下の出力があるか確認すること。なければ追加が必要。
print(f"poem_wrapped={poem_wrapped}")
print(f"poem_first_line={poem_lines[0]}")

### 詩のストックが少ない
現在12本しかない。毎日1本投稿すると約12日で尽きる。
早めに30〜60本追加登録しておくと安心。

### ローカルテスト時の注意
post_x.pyはrequests-oauthlibを使用。ローカルでテストする場合は以下が必要。
pip install requests-oauthlib

## 未完了タスク（優先順）

### 1. Instagram投稿 — 400 Bad Request
状況：post_instagram.pyで投稿するとエラーが出る。
やること：Instagram Graph APIの設定を見直す。次回作業時に現状のエラー内容を見てから対応。

### 2. TikTok — storageQuotaExceeded
状況：Service AccountはGoogleドライブのストレージクォータを持たないためエラーが出る。
やること：アップロード先を共有ドライブに変更するか、OAuthでオーナー（tamanotameiki@gmail.com）のDriveに直接アップロードする方式に書き直す。

### 3. Pinterest — Standard申請
状況：Trialアクセスのままでは投稿APIが使えない。"consumer type is not supported"エラー。
やること：https://developers.pinterest.com/ からアクセスレベルの格上げを申請する。無料・審査あり。

### 4. YouTubeサムネイル自動設定
状況：thumbnails.set APIで403 forbidden。チャンネルが「認証済み」でないと使えない。
やること：チャンネルの電話番号認証を行ってから再挑戦。もしくは認証なしのまま運用（後回し可）。

### 5. YouTubeエンドスクリーン自動設定
状況：insufficientPermissionsエラー。OAuthスコープにyoutube.force-sslが含まれていない。
やること：
1. E:\tamanotameiki_system\get_youtube_token.py を開く
2. SCOPESにhttps://www.googleapis.com/auth/youtube.force-sslを追加
3. スクリプトを実行してトークンを再取得
4. 新しいyoutube_credentials.jsonの内容をGitHub SecretsのYOUTUBE_CREDENTIALSに上書き登録

### 6. スプレッドシート「ダッシュボード」シート作成
状況：シートがまだない。
やること：投稿履歴データをもとに自動集計されるダッシュボードシートを設計・作成する。
表示内容：推移グラフ・ヒートマップ・タグ別平均・詩ストック残数など。

### 7. LINE通知の代替
状況：LINE Notifyが2025年3月にサービス終了。現在のnotify_line.pyは動かない。
やること：代替手段を決める。候補：メール通知（Gmail API）・Discord Webhook・Slack Webhook。

### 8. 公式HP — Pinterest追加・スマホ対応
状況：docs/index.htmlにPinterestリンクがない。スマホレイアウト未調整。
やること：PinterestアイコンとURLを追加。CSSにメディアクエリを追加してスマホ表示を整える。