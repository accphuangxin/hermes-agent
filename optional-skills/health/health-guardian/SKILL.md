---
name: health-guardian
description: >
  个人健康管家。基于用户 Profile（年龄、体重、身高、慢性病史、用药情况、运动习惯、睡眠模式）
  提供每日健康检查、营养跟踪、运动计划、睡眠分析、症状初步评估和复诊提醒。
  纯离线计算 + 免费公开 API，无需付费订阅。
platforms: [linux, macos, windows]
version: 1.0.0
authors:
  - huangxin
license: MIT
metadata:
  hermes:
    tags: [health, wellness, nutrition, fitness, sleep, medication, chronic-disease, profile, 健康, 管家]
    category: health
    related_skills: [fitness-nutrition, neuroskill-bci]
    prerequisites:
      commands: [python3, curl]
required_environment_variables:
  - name: USDA_API_KEY
    prompt: "USDA FoodData Central API key（免费）"
    help: "https://fdc.nal.usda.gov/api-key-signup/ 免费注册，或留空使用 DEMO_KEY（30次/小时）"
    optional: true
---

# 健康管家 (Health Guardian)

> **声明**：本技能仅供健康管理参考，不构成医疗诊断或治疗建议。
> 任何症状或用药疑问请咨询执业医师。

基于用户健康档案（Profile）提供个性化的健康管理服务：每日健康检查、
营养跟踪、运动建议、睡眠分析、症状初步评估、慢性病自我管理和复诊提醒。

---

## 触发条件

当用户提到以下任何场景时加载此 skill：

- 健康打卡 / 今天状态 / 我感觉不舒服
- 吃了什么 / 热量 / 营养 / 饮食记录
- 运动计划 / 今天锻炼 / 步数 / 跑步
- 睡眠 / 昨晚睡了几小时 / 失眠
- 血压 / 血糖 / 体重 / 体检
- 用药提醒 / 忘记吃药 / 药量
- 慢性病管理 / 高血压 / 糖尿病 / 心脏病
- 症状 / 头疼 / 发烧 / 疲劳 / 需要看医生吗

---

## 核心功能模块

### 模块 0 — Profile 加载与建立

**用户档案存储位置**：`~/.hermes/memories/health_profile.json`（或当前 profile 的 memories 目录）

档案结构：
```json
{
  "basic": {
    "name": "用户昵称",
    "age": 35,
    "gender": "M",
    "height_cm": 175,
    "weight_kg": 70.0,
    "blood_type": "A+"
  },
  "medical": {
    "chronic_conditions": ["高血压", "2型糖尿病"],
    "medications": [
      {"name": "二甲双胍", "dose": "500mg", "frequency": "每日两次", "with_meal": true},
      {"name": "厄贝沙坦", "dose": "150mg", "frequency": "每日一次", "time": "早晨"}
    ],
    "allergies": ["青霉素"],
    "doctor_name": "王医生",
    "next_appointment": "2026-07-15"
  },
  "lifestyle": {
    "activity_level": 3,
    "sleep_target_hours": 8.0,
    "wake_time": "07:00",
    "sleep_time": "23:00",
    "diet_restrictions": ["低盐", "低GI"]
  },
  "goals": {
    "target_weight_kg": 65.0,
    "target_steps_per_day": 8000,
    "target_water_ml": 2000
  },
  "metrics_today": {
    "date": "",
    "weight_kg": null,
    "steps": null,
    "sleep_hours": null,
    "water_ml": 0,
    "bp_systolic": null,
    "bp_diastolic": null,
    "blood_glucose_mmol": null,
    "mood": null,
    "energy_level": null
  }
}
```

**首次使用**：若档案不存在，引导用户填写基本信息，再保存档案。

```python
import json, os
from pathlib import Path

# 寻找 hermes memories 目录
memories_dir = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories"
memories_dir.mkdir(parents=True, exist_ok=True)
profile_path = memories_dir / "health_profile.json"

if profile_path.exists():
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    print("✅ 健康档案已加载")
    b = profile["basic"]
    print(f"   {b.get('name','用户')} | {b.get('age','?')}岁 | {b.get('height_cm','?')}cm | {b.get('weight_kg','?')}kg")
    m = profile["medical"]
    if m.get("chronic_conditions"):
        print(f"   慢性病：{', '.join(m['chronic_conditions'])}")
    if m.get("medications"):
        print(f"   用药：{len(m['medications'])} 种")
else:
    print("⚠️  未找到健康档案，请告诉我你的基本信息来建立档案。")
    print("   需要：姓名/昵称、年龄、性别、身高、体重")
    print("   可选：慢性病史、用药情况、饮食禁忌、健康目标")
```

**保存/更新档案**：
```python
profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
print("💾 档案已保存")
```

---

### 模块 1 — 每日健康打卡

收集当日关键指标，与历史均值和目标比较，生成日报。

```python
import json, datetime
from pathlib import Path
import os

profile_path = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories" / "health_profile.json"
log_path = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories" / "health_log.jsonl"

today = datetime.date.today().isoformat()

# 根据用户输入更新 metrics_today（由对话上下文填充）
# 示例：用户说"体重70.2，血压125/82，睡了7小时，走了6200步"
metrics = {
    "date": today,
    "weight_kg": 70.2,       # 从对话中提取
    "bp_systolic": 125,
    "bp_diastolic": 82,
    "sleep_hours": 7.0,
    "steps": 6200,
    "water_ml": 1500,
    "blood_glucose_mmol": None,
    "mood": "一般",
    "energy_level": 3,       # 1-5
}

# 追加到日志
with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(metrics, ensure_ascii=False) + "\n")

# 读取最近 7 天计算均值
if log_path.exists():
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    recent = lines[-7:]
    def avg(key): vals = [r[key] for r in recent if r.get(key) is not None]; return sum(vals)/len(vals) if vals else None
    print(f"📊 近7日均值：体重 {avg('weight_kg'):.1f}kg | 睡眠 {avg('sleep_hours'):.1f}h | 步数 {int(avg('steps') or 0):,}")
```

**日报评估逻辑**（纯 Python，无依赖）：

```python
def daily_assessment(metrics, profile):
    goals = profile.get("goals", {})
    medical = profile.get("medical", {})
    alerts = []
    tips = []

    # 血压评估
    sbp, dbp = metrics.get("bp_systolic"), metrics.get("bp_diastolic")
    if sbp and dbp:
        if sbp >= 140 or dbp >= 90:
            alerts.append(f"⚠️ 血压偏高 {sbp}/{dbp} mmHg，建议休息并复测")
        elif sbp >= 130 or dbp >= 80:
            tips.append(f"📌 血压轻度升高 {sbp}/{dbp}，保持低盐饮食")
        else:
            tips.append(f"✅ 血压正常 {sbp}/{dbp}")

    # 血糖评估（餐后2小时参考值 <7.8，空腹 <6.1）
    bg = metrics.get("blood_glucose_mmol")
    if bg:
        if bg > 11.1:
            alerts.append(f"🚨 血糖显著升高 {bg} mmol/L，请联系医生")
        elif bg > 7.8:
            alerts.append(f"⚠️ 血糖偏高 {bg} mmol/L，注意饮食")
        else:
            tips.append(f"✅ 血糖正常 {bg} mmol/L")

    # 睡眠评估
    sleep = metrics.get("sleep_hours")
    target_sleep = profile.get("lifestyle", {}).get("sleep_target_hours", 8)
    if sleep:
        if sleep < 6:
            alerts.append(f"⚠️ 睡眠不足 {sleep}h，建议早休息")
        elif sleep < target_sleep - 1:
            tips.append(f"📌 睡眠略少 {sleep}h（目标{target_sleep}h）")
        else:
            tips.append(f"✅ 睡眠良好 {sleep}h")

    # 步数评估
    steps = metrics.get("steps")
    target_steps = goals.get("target_steps_per_day", 8000)
    if steps is not None:
        pct = steps / target_steps * 100
        if pct >= 100:
            tips.append(f"🏃 步数达标！{steps:,} 步（目标{target_steps:,}）")
        elif pct >= 70:
            tips.append(f"👟 步数 {steps:,}，距目标还差 {target_steps - steps:,} 步")
        else:
            tips.append(f"💡 今日活动较少 {steps:,} 步，建议饭后散步")

    # 饮水评估
    water = metrics.get("water_ml", 0)
    target_water = goals.get("target_water_ml", 2000)
    if water < target_water * 0.7:
        tips.append(f"💧 饮水不足 {water}ml（目标{target_water}ml），注意多喝水")

    return alerts, tips

alerts, tips = daily_assessment(metrics, profile)
print("\n=== 今日健康日报 ===")
for a in alerts: print(a)
for t in tips: print(t)
```

---

### 模块 2 — 营养与饮食跟踪

复用 fitness-nutrition skill 中的 USDA API，并针对慢性病用户增加定制过滤。

```bash
# 查询食物营养（支持中文拼音/英文）
FOOD="${1:-rice}"
API_KEY="${USDA_API_KEY:-DEMO_KEY}"
ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$FOOD")
curl -s "https://api.nal.usda.gov/fdc/v1/foods/search?api_key=${API_KEY}&query=${ENCODED}&pageSize=5&dataType=Foundation,SR%20Legacy" \
  | python3 -c "
import json,sys
data=json.load(sys.stdin)
for f in data.get('foods',[]):
    n={x['nutrientName']:x.get('value','?') for x in f.get('foodNutrients',[])}
    kcal=n.get('Energy','?'); prot=n.get('Protein','?')
    fat=n.get('Total lipid (fat)','?'); carb=n.get('Carbohydrate, by difference','?')
    sodium=n.get('Sodium, Na','?')
    print(f\"{f.get('description','')}\")
    print(f\"  每100g: {kcal}kcal | 蛋白{prot}g | 脂肪{fat}g | 碳水{carb}g | 钠{sodium}mg\")
"
```

**慢性病饮食红绿灯**（根据 Profile 自动生成提示）：

```python
def diet_traffic_light(food_name, nutrients, chronic_conditions):
    """
    nutrients: dict with keys Energy, Protein, Total lipid (fat),
               Carbohydrate by difference, Sodium Na, Sugars total
    """
    warnings = []
    conditions = [c.lower() for c in chronic_conditions]

    sodium = float(nutrients.get("Sodium, Na") or 0)
    sugar = float(nutrients.get("Sugars, total including NLEA") or nutrients.get("Sugars, total") or 0)
    carb = float(nutrients.get("Carbohydrate, by difference") or 0)
    fat = float(nutrients.get("Total lipid (fat)") or 0)
    kcal = float(nutrients.get("Energy") or 0)

    # 高血压：限钠
    if any(k in conditions for k in ["高血压", "hypertension"]):
        if sodium > 400:  # 每100g > 400mg 钠
            warnings.append(f"🔴 高钠食物 ({sodium}mg/100g)，高血压患者需限量")
        elif sodium > 200:
            warnings.append(f"🟡 中等含钠 ({sodium}mg/100g)，注意摄入总量")

    # 糖尿病：限糖限高GI碳水
    if any(k in conditions for k in ["糖尿病", "diabetes", "2型糖尿病"]):
        if sugar > 15:
            warnings.append(f"🔴 高糖食物 ({sugar}g/100g)，糖尿病患者避免")
        elif carb > 50:
            warnings.append(f"🟡 高碳水 ({carb}g/100g)，注意血糖影响，搭配蛋白质")

    # 心脏病：限饱和脂肪
    if any(k in conditions for k in ["心脏病", "heart disease", "冠心病"]):
        if fat > 20:
            warnings.append(f"🟡 脂肪含量较高 ({fat}g/100g)，心血管患者需控制")

    if not warnings:
        warnings.append("🟢 该食物对你的健康状况无特别禁忌")
    return warnings
```

**每日膳食记录与热量汇总**：

```python
# 追加饮食记录到当日日志
meal_record = {
    "date": today,
    "meal": "午餐",       # 早餐/午餐/晚餐/加餐
    "food": "米饭",
    "amount_g": 200,
    "kcal": 260,          # 从 USDA API 换算
    "protein_g": 4.8,
    "carb_g": 57.4,
    "fat_g": 0.4,
    "sodium_mg": 2,
}
meal_log_path = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories" / "meal_log.jsonl"
with open(meal_log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(meal_record, ensure_ascii=False) + "\n")

# 今日热量汇总
if meal_log_path.exists():
    today_meals = [json.loads(l) for l in meal_log_path.read_text(encoding="utf-8").splitlines()
                   if l.strip() and json.loads(l).get("date") == today]
    total_kcal = sum(m.get("kcal", 0) for m in today_meals)
    total_sodium = sum(m.get("sodium_mg", 0) for m in today_meals)
    print(f"今日摄入：{total_kcal:.0f} kcal | 钠 {total_sodium:.0f} mg")
```

---

### 模块 3 — 运动计划生成

根据 Profile（年龄、体重、慢性病、活动水平）生成个性化运动建议。

```python
def generate_workout_plan(profile):
    basic = profile["basic"]
    medical = profile["medical"]
    lifestyle = profile["lifestyle"]
    goals = profile["goals"]

    age = basic.get("age", 30)
    weight = basic.get("weight_kg", 70)
    conditions = [c.lower() for c in medical.get("chronic_conditions", [])]
    activity = lifestyle.get("activity_level", 3)  # 1(久坐) - 5(运动员)

    # 心率安全范围
    max_hr = 220 - age
    moderate_hr_low = int(max_hr * 0.50)
    moderate_hr_high = int(max_hr * 0.70)
    vigorous_hr = int(max_hr * 0.85)

    plan = {
        "heart_rate_zone": f"中等强度 {moderate_hr_low}-{moderate_hr_high} bpm",
        "max_hr_warning": f"⚠️ 不超过 {vigorous_hr} bpm",
        "weekly_cardio_min": 150,
        "weekly_strength_sessions": 2,
        "exercises": [],
        "avoid": [],
        "notes": [],
    }

    # 慢性病禁忌调整
    if any(k in conditions for k in ["高血压", "hypertension"]):
        plan["avoid"].append("重量过大的无氧训练（Valsalva 动作）")
        plan["avoid"].append("倒立/头低脚高体位")
        plan["notes"].append("运动前后各测一次血压，收缩压 >180 时停止运动")
        plan["exercises"] += ["快步走", "游泳", "骑自行车", "太极拳"]

    if any(k in conditions for k in ["糖尿病", "diabetes"]):
        plan["notes"].append("运动前检测血糖：<5.5 先加餐，>16.7 暂缓运动")
        plan["notes"].append("随身携带糖果或果汁，防止低血糖")
        plan["exercises"] += ["饭后30分钟步行20分钟", "抗阻训练（增加胰岛素敏感性）"]

    if any(k in conditions for k in ["心脏病", "冠心病", "heart"]):
        plan["weekly_cardio_min"] = 150
        plan["notes"].append("出现胸痛/胸闷/极度呼吸困难立即停止并就医")
        plan["exercises"] += ["散步", "太极", "低强度水中运动"]
        plan["avoid"].append("高强度间歇训练(HIIT)")

    # 默认推荐（无禁忌或通用建议）
    if not plan["exercises"]:
        if activity <= 2:
            plan["exercises"] = ["每日步行30分钟", "拉伸10分钟"]
        elif activity == 3:
            plan["exercises"] = ["慢跑20分钟", "力量训练3组", "每日8000步"]
        else:
            plan["exercises"] = ["自定义训练计划，保持现有节奏"]

    return plan

plan = generate_workout_plan(profile)
print("=== 个人运动方案 ===")
print(f"目标心率：{plan['heart_rate_zone']}")
print(f"{plan['max_hr_warning']}")
print(f"推荐运动：{', '.join(plan['exercises'])}")
if plan["avoid"]:
    print(f"⛔ 禁忌：{'; '.join(plan['avoid'])}")
for note in plan["notes"]:
    print(note)
```

---

### 模块 4 — 用药提醒与跟踪

```python
import datetime

def check_medications(profile):
    medications = profile.get("medical", {}).get("medications", [])
    if not medications:
        print("📋 未配置用药信息")
        return

    now = datetime.datetime.now()
    hour = now.hour
    print(f"=== 用药提醒 ({now.strftime('%H:%M')}) ===")

    for med in medications:
        name = med.get("name", "未知药物")
        dose = med.get("dose", "")
        freq = med.get("frequency", "")
        with_meal = med.get("with_meal", False)
        time_pref = med.get("time", "")

        reminder = f"💊 {name} {dose} — {freq}"
        if with_meal:
            reminder += "（随餐服用）"
        if time_pref:
            reminder += f"（建议{time_pref}服用）"
        print(reminder)

    # 下次复诊提醒
    next_appt = profile.get("medical", {}).get("next_appointment", "")
    if next_appt:
        days_left = (datetime.date.fromisoformat(next_appt) - datetime.date.today()).days
        if days_left <= 7:
            print(f"🏥 复诊提醒：{next_appt}（还有{days_left}天），请提前准备检查结果")
        elif days_left <= 30:
            print(f"📅 复诊日期：{next_appt}（{days_left}天后）")

check_medications(profile)
```

---

### 模块 5 — 症状初步评估

基于规则引擎对用户描述的症状进行初步分类，**不作诊断**，仅提供就医建议。

```python
SYMPTOM_RULES = [
    # (关键词列表, 严重级别 1-3, 建议)
    (["胸痛", "胸闷", "压榨感", "左臂痛", "心跳骤停"], 3,
     "🚨 立即拨打120！可能的心脏急症"),
    (["中风", "面部歪斜", "突然失语", "手臂无力", "剧烈头痛"], 3,
     "🚨 立即拨打120！可能的脑卒中（FAST原则：脸/臂/言语/时间）"),
    (["高烧", "体温39", "体温40", "惊厥", "抽搐"], 3,
     "🚨 立即就医！高热/惊厥需急诊处理"),
    (["血压160", "血压180", "血压200", "高血压危象"], 2,
     "⚠️ 血压危象风险，立即就医，避免剧烈活动"),
    (["血糖20", "血糖25", "意识模糊", "酮症"], 2,
     "⚠️ 可能高血糖急症，立即就医"),
    (["低血糖", "血糖3", "冷汗颤抖", "饥饿心慌"], 2,
     "⚠️ 低血糖反应，立即补充15g糖（糖果/果汁），15分钟后复测"),
    (["发烧", "体温38", "咳嗽", "喉咙痛", "乏力"], 1,
     "💊 疑似感冒/流感，多休息多喝水，持续3天以上或加重请就医"),
    (["头晕", "眩晕", "恶心"], 1,
     "💡 注意休息，测量血压和血糖。若持续或伴呕吐请就医"),
    (["失眠", "睡不着", "难以入睡"], 1,
     "💤 建议：固定作息，睡前1小时避免屏幕，可尝试放松呼吸练习"),
    (["疲劳", "乏力", "没精神"], 1,
     "😴 注意睡眠质量、饮食营养和适度运动。持续2周以上请就医排查贫血/甲状腺"),
]

def assess_symptoms(user_input, chronic_conditions=None):
    chronic_conditions = chronic_conditions or []
    user_input_lower = user_input.lower()
    matched = []

    for keywords, level, advice in SYMPTOM_RULES:
        if any(kw in user_input_lower for kw in keywords):
            matched.append((level, advice))

    if not matched:
        return [( 0, "ℹ️ 未识别到特定症状关键词，请详细描述你的感受，我来帮你判断是否需要就医。")]

    # 按严重程度排序，显示最高优先级
    matched.sort(key=lambda x: -x[0])
    return matched[:3]

# 示例调用
symptoms = assess_symptoms("我感觉胸口有点闷，今天血压160/95", profile.get("medical", {}).get("chronic_conditions", []))
for _, advice in symptoms:
    print(advice)
```

---

### 模块 6 — 健康趋势周报

读取最近7天日志，生成可视化文字趋势报告。

```python
import json
from pathlib import Path
import os

log_path = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "memories" / "health_log.jsonl"

def weekly_report(log_path, profile):
    if not log_path.exists():
        print("📭 暂无健康日志数据，开始每日打卡后可生成周报")
        return

    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    week = sorted(lines, key=lambda x: x.get("date", ""))[-7:]

    if len(week) < 2:
        print("📊 数据不足，至少需要2天打卡记录")
        return

    def field_trend(key, unit="", fmt=".1f"):
        vals = [(r["date"][-5:], r[key]) for r in week if r.get(key) is not None]
        if not vals: return
        avg_val = sum(v for _,v in vals) / len(vals)
        trend = "↗" if vals[-1][1] > vals[0][1] else ("↘" if vals[-1][1] < vals[0][1] else "→")
        bar = " ".join(f"{d}:{v:{fmt}}" for d,v in vals)
        print(f"  {key:<15} 均值:{avg_val:{fmt}}{unit} {trend}  [{bar}]")

    print("=== 健康趋势周报 ===")
    goals = profile.get("goals", {})
    field_trend("weight_kg", "kg")
    field_trend("sleep_hours", "h")
    field_trend("steps", "", ".0f")
    field_trend("bp_systolic", "mmHg", ".0f")
    field_trend("blood_glucose_mmol", "mmol/L")

    # 综合评分（满分100）
    score = 60
    avgs = {k: sum(r[k] for r in week if r.get(k) is not None) / max(1, sum(1 for r in week if r.get(k) is not None))
            for k in ["sleep_hours", "steps", "water_ml"]}
    if avgs.get("sleep_hours", 0) >= 7: score += 10
    if avgs.get("steps", 0) >= goals.get("target_steps_per_day", 8000): score += 15
    if avgs.get("water_ml", 0) >= goals.get("target_water_ml", 2000): score += 10
    if len(week) >= 5: score += 5  # 打卡坚持奖励
    print(f"\n  本周健康评分：{min(score, 100)}/100")

weekly_report(log_path, profile)
```

---

## 对话流程

### 首次使用
1. 检测 `health_profile.json` 是否存在
2. 不存在 → 友好引导建档（逐步提问，不要一次性要求太多信息）
3. 存在 → 加载档案，进入主菜单

### 日常交互
- **"早安" / "今天打卡"** → 模块1（每日检查）
- **"吃了/喝了/午饭"** → 模块2（营养跟踪）
- **"运动/锻炼计划"** → 模块3（运动建议）
- **"吃药了吗/用药提醒"** → 模块4（用药管理）
- **"不舒服/症状"** → 模块5（症状评估）
- **"周报/趋势"** → 模块6（健康报告）
- **"更新档案/修改信息"** → 模块0（档案编辑）

---

## 数据文件说明

| 文件 | 内容 |
|------|------|
| `memories/health_profile.json` | 用户健康档案（基本信息、慢性病、用药） |
| `memories/health_log.jsonl` | 每日打卡日志（每行一条 JSON） |
| `memories/meal_log.jsonl` | 饮食记录日志 |

---

## 重要原则

1. **先问诊后建议**：不确定用户状况时，先问清楚再给建议
2. **慢性病优先**：Profile 中有慢性病时，所有建议都必须考虑禁忌
3. **严重症状立即升级**：3级症状直接建议急诊，不做过多分析
4. **不替代医生**：每次涉及用药调整或症状判断时，明确建议"咨询医生"
5. **鼓励打卡**：用正向反馈激励用户坚持记录健康数据

---

## 验证

- 档案加载后：确认姓名/年龄/慢性病列表正确显示
- 营养查询后：确认每100g 热量/蛋白质/脂肪/碳水数据返回
- 运动计划后：慢性病用户必须包含禁忌提示
- 症状评估后：3级症状必须显示急诊建议
