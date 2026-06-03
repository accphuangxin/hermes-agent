---
name: pharma-drug-match
description: "从 Excel 读取药品信息，按每组50条拆批，并行调用商品匹配 API，聚合结果后写回新 Excel。"
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [pharma, drug, excel, batch, parallel, matching, 药品, 匹配]
    category: domain
---

# 药品商品批量匹配 Skill

从 Excel 文件读取药品基本信息（品牌、商品名称、规格、生产厂商、批准文号、上市许可持有人等），
按每组 50 条拆批后**并行**调用商品匹配 API，最终将所有匹配结果聚合写入新 Excel 文件。

## 触发条件

用户提到以下任意场景时加载此 skill：
- 药品 Excel 批量匹配
- 药品信息对照 / 商品匹配
- 药品数据并行处理

---

## 执行步骤

### Step 1 — 确认输入参数

向用户确认以下信息（如果消息里已有则跳过）：

| 参数 | 说明 | 示例 |
|------|------|------|
| `input_file` | 输入 Excel 路径 | `/data/drugs.xlsx` |
| `api_url` | 匹配 API 地址 | `https://api.example.com/match` |
| `api_key` | API 鉴权 Key（可选） | `Bearer xxx` |
| `output_file` | 输出 Excel 路径 | `/data/drugs_matched.xlsx`（默认同目录加 `_matched`） |
| `batch_size` | 每批条数（默认 50） | `50` |
| `sheet_name` | Sheet 名（默认第一个） | `Sheet1` |

---

### Step 2 — 读取并拆批

用 `execute_code` 运行以下 Python，读取 Excel 并输出拆批结果供后续使用：

```python
import pandas as pd
import json, math, os

input_file = "<用户提供的路径>"
batch_size = 50
sheet_name = 0  # 默认第一个 sheet

df = pd.read_excel(input_file, sheet_name=sheet_name, dtype=str)
df = df.fillna("")

# 规范列名（去首尾空格）
df.columns = [c.strip() for c in df.columns]

total = len(df)
num_batches = math.ceil(total / batch_size)

print(f"总记录数: {total}")
print(f"批次数量: {num_batches}（每批 {batch_size} 条）")
print(f"列名: {list(df.columns)}")

# 将每批数据序列化为 JSON 字符串，供 subagent 使用
batches = []
for i in range(num_batches):
    chunk = df.iloc[i*batch_size : (i+1)*batch_size]
    batches.append({
        "batch_index": i,
        "start_row": i * batch_size,
        "end_row": min((i+1)*batch_size, total),
        "records": chunk.to_dict(orient="records"),
    })

# 保存到临时文件，让 subagent 读取
tmp_dir = os.path.dirname(input_file)
batches_file = os.path.join(tmp_dir, "_drug_batches.json")
with open(batches_file, "w", encoding="utf-8") as f:
    json.dump(batches, f, ensure_ascii=False, indent=2)

print(f"拆批文件已保存: {batches_file}")
```

---

### Step 3 — 并行调用 subagent

读取拆批文件后，构建 `delegate_task` 的 tasks 数组，**每个 subagent 处理一批**：

```python
import json

with open(batches_file, "r", encoding="utf-8") as f:
    batches = json.load(f)

# 为每批构建 subagent 任务描述
tasks = []
for batch in batches:
    tasks.append({
        "goal": f"""
调用药品商品匹配 API，处理第 {batch['batch_index']+1} 批（第 {batch['start_row']+1}~{batch['end_row']} 条）。

## 输入数据
从文件读取本批数据：
- 拆批文件路径：{batches_file}
- 本批 batch_index：{batch['batch_index']}

## API 信息
- URL：<api_url>
- Key：<api_key>（如有）

## 执行要求
1. 读取拆批文件，取 batch_index={batch['batch_index']} 的数据
2. 对每条记录调用匹配 API（可逐条或批量，视 API 文档而定）
3. 将原始字段 + API 返回的匹配结果合并为一条记录
4. 将本批结果写入文件：{os.path.dirname(batches_file)}/_result_batch_{batch['batch_index']:03d}.json
5. 写入格式：JSON 数组，每个元素包含原始字段 + match_result 字段
6. 输出：完成后打印 "batch {batch['batch_index']} done, {batch['end_row']-batch['start_row']} records"

## 错误处理
- 单条 API 调用失败时，match_result 填写 {{"error": "错误信息", "status": "failed"}}，继续处理下一条
- 不要因单条失败而中止整批
""",
        "context": "你是一个数据处理 worker，只负责调用 API 并写入结果文件，不需要做其他事情。",
        "toolsets": ["hermes-cli"],
    })
```

然后调用 `delegate_task`（批量模式）：

```json
{
  "tasks": [ /* 上面构建的 tasks 数组 */ ]
}
```

> **注意**：并发数受 `config.yaml` 的 `delegation.max_concurrent_children` 控制（默认 3）。
> 如果批次较多（如 20 批），建议设为 10：
> ```bash
> hermes config set delegation.max_concurrent_children 10
> ```

---

### Step 4 — 等待并收集结果

`delegate_task` 返回后，所有 subagent 已完成。用 `execute_code` 收集结果文件：

```python
import json, os, glob

tmp_dir = "<拆批文件所在目录>"
result_files = sorted(glob.glob(os.path.join(tmp_dir, "_result_batch_*.json")))

print(f"找到结果文件: {len(result_files)} 个")

all_results = []
failed_batches = []

for f in result_files:
    try:
        with open(f, "r", encoding="utf-8") as fp:
            batch_results = json.load(fp)
        all_results.extend(batch_results)
    except Exception as e:
        batch_idx = f.split("_batch_")[-1].replace(".json", "")
        failed_batches.append({"file": f, "error": str(e)})
        print(f"⚠ 读取失败: {f} — {e}")

print(f"汇总记录数: {len(all_results)}")
if failed_batches:
    print(f"⚠ 失败批次: {failed_batches}")
```

---

### Step 5 — 生成结果 Excel

```python
import pandas as pd
import json, os
from datetime import datetime

# all_results 已在上一步加载
df_result = pd.DataFrame(all_results)

# match_result 是 dict，展开为独立列
if "match_result" in df_result.columns:
    match_expanded = pd.json_normalize(df_result["match_result"].apply(
        lambda x: x if isinstance(x, dict) else {}
    ))
    match_expanded.columns = [f"match_{c}" for c in match_expanded.columns]
    df_result = pd.concat([df_result.drop(columns=["match_result"]), match_expanded], axis=1)

# 输出路径
input_file = "<原始输入文件路径>"
output_file = input_file.replace(".xlsx", f"_matched_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    df_result.to_excel(writer, sheet_name="匹配结果", index=False)

    # 统计 sheet
    total = len(df_result)
    success = df_result.get("match_status", pd.Series()).eq("success").sum() if "match_status" in df_result else 0
    failed = df_result.get("match_error", pd.Series()).notna().sum() if "match_error" in df_result else 0
    stats = pd.DataFrame([
        {"指标": "总记录数", "数值": total},
        {"指标": "匹配成功", "数值": int(success)},
        {"指标": "匹配失败", "数值": int(failed)},
        {"指标": "生成时间", "数值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ])
    stats.to_excel(writer, sheet_name="统计", index=False)

print(f"✓ 结果文件已生成: {output_file}")
print(f"  总记录: {total} 条")
```

---

### Step 6 — 清理临时文件（可选）

```python
import glob, os

tmp_files = glob.glob(os.path.join(tmp_dir, "_drug_batches.json")) + \
            glob.glob(os.path.join(tmp_dir, "_result_batch_*.json"))

for f in tmp_files:
    os.remove(f)
    print(f"已删除: {f}")
```

---

### Step 7 — 回复用户

告知用户：
- 输出文件路径
- 总处理条数
- 成功/失败数量
- 是否有需要人工复查的失败记录

---

## API 调用模板参考

subagent 调用 API 时，根据接口文档选择以下模式：

**逐条模式（每条单独请求）：**
```python
import requests, json

api_url = "<api_url>"
headers = {"Authorization": "<api_key>", "Content-Type": "application/json"}

results = []
for record in batch_records:
    payload = {
        "brand": record.get("品牌", ""),
        "name": record.get("商品名称", ""),
        "spec": record.get("规格", ""),
        "manufacturer": record.get("生产厂商", ""),
        "approval_no": record.get("批准文号", ""),
        "mah": record.get("上市许可持有人", ""),
    }
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        match_result = resp.json()
    except Exception as e:
        match_result = {"error": str(e), "status": "failed"}
    results.append({**record, "match_result": match_result})
```

**批量模式（一次请求多条）：**
```python
payload = {"items": batch_records}
resp = requests.post(api_url, json=payload, headers=headers, timeout=60)
api_results = resp.json().get("results", [])
results = [{**record, "match_result": api_result}
           for record, api_result in zip(batch_records, api_results)]
```

---

## 常见问题

**Q：subagent 数量上限？**
受 `delegation.max_concurrent_children` 控制。500条/50=10批，建议设为 10。

**Q：某批 subagent 失败了怎么办？**
检查对应的 `_result_batch_XXX.json` 是否生成。没生成说明 subagent 整体失败，
可手动重跑该批：重新调用 `delegate_task` 只传该批的 task。

**Q：API 有限流怎么办？**
在 subagent 的 goal 里加入：`每次请求后 sleep(0.5)` 或降低 `max_concurrent_children`。

**Q：Excel 列名和模板不一致？**
Step 2 会打印实际列名，根据打印结果调整 API 调用模板里的字段映射。
