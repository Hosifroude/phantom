# 通常ターンプロンプト

仮想企業「ファントム」の4時間ターンを生成してください。会社状態、社員状態、直近ログをもとに、社員3人分の行動を1つのJSONで返してください。勤務時間は固定せず、現在時刻、曜日、疲労、モチベーション、案件状況、個人資金を考慮してください。

## 状態変化と時間の出力ルール

各社員オブジェクトでは、必ずトップレベルに `hours_used` を入れ、4時間ターンで実行した `actions[*].duration_hours` の合計値（最大4.0）を設定してください。

状態変化は `status_change` を使わず、必ず `effects` に以下のキーで入れてください。

```json
"hours_used": 4.0,
"effects": {
  "fatigue_delta": -2,
  "motivation_delta": 1
}
```

`effects.fatigue_delta` と `effects.motivation_delta` は0のままにせず、行動結果として実際に増減した値を入れてください。
