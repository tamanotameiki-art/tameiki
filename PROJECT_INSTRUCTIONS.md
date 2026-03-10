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
- daily_post.yml: 毎日自動投稿（YouTube・Instagram・X・TikTok）
- collect_analytics.yml: 毎日23:00 UTC（8:00 JST）にYouTube・Instagram反応数収集
- refresh_instagram_token.yml: 毎月1日にInstagramトークン自動リフレッシュ
- bgm_mastering.yml: BGMマスタリング

## スクリプト一覧（scripts/）
- post_youtube.py: YouTube Shorts投稿（OAuth2）
- post_instagram.py: Instagram投稿（400エラー未解決）
- post_x.py: X投稿
- post_pinterest.py: Pinterest投稿（Standard申請待ち）
- prepare_tiktok.py: TikTok投稿準備（storageQuotaExceededエラー未解決）
- collect_analytics.py: YouTube・Instagram反応数収集（直近30本）
- generate_captions.py: キャプション生成
- generate_images.py: 画像生成
- run_generate.py: メイン生成スクリプト
- bgm_mastering.py: BGMマスタリング

## 完了済みタスク
- Instagramプロアカウント設定・Facebookページ連携
- Meta for Developers「tameiki-system」アプリ設定・テスター登録
- システムユーザー「tameiki-bot」作成・権限付与
- Instagramトークン毎月自動リフレッシュ（refresh_instagram_token.yml）
- collect_analytics.py作成・動作確認完了
- スプレッドシート投稿履歴シートに反応数列を自動追加

## 未完了タスク（優先順）
1. post_instagram.py: 400 Bad Request エラー解消
2. TikTok: storageQuotaExceededエラー解消
3. Pinterest: Standard申請（法人不要・個人でも申請可能か要確認）
4. YouTube: サムネイル・エンドスクリーン設定（スコープ不足）
5. ダッシュボードシート作成
6. LINE通知の代替手段を決める