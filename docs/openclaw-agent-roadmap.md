# OpenClaw-Style Agent Roadmap (RevenueCat Agent)

## 1) Hedef
- Agent'i sadece task-trigger sisteminden çıkarıp `Agent.md + SKILL.md` tabanlı, davranışı sözleşmeyle tanımlı bir operatöre dönüştürmek.
- OpenClaw benzeri bir panelden agent'i yönetmek (prompt, skill set, approvals, memory görünürlüğü).

## 2) Memory Kararı
- **Karar: Hybrid** (katmanlı memory + periyodik compile).
- Sadece katmanlı memory: izlenebilir ama zamanla şişer.
- Sadece compile: ucuz ama ham bağlam kaybı olur.
- Hybrid ile hem denetlenebilirlik hem düşük token maliyeti korunur.

## 3) Hedef Mimari
- `Agent.md`: kimlik, amaç, guardrail, karar ilkeleri, KPI önceliği.
- `SKILL.md`: araç kontratı, input/output şeması, risk seviyesi, test örnekleri.
- Runtime:
  - Planner (ne yapılacak),
  - Skill selector (hangi skill),
  - Executor (nasıl çalıştırılacak),
  - Critic (çıktı kalite/safety kontrolü).
- Memory:
  - L0 Working context (anlık oturum),
  - L1 Episodic events (ham olay),
  - L2 Semantic memory (pgvector),
  - L3 Compiled summaries (saatlik/günlük/haftalık),
  - L4 Policy memory (Agent.md + skill kuralları).

## 4) Fazlar

### Faz 0 (1-2 gün) - Contract Layer
- `agent/AGENT.md` dosya formatını sabitle.
- `skills/*/SKILL.md` için metadata standardı çıkar:
  - `name`, `scope`, `risk_level`, `requires_approval`, `inputs`, `outputs`, `tests`.
- `agent_contract_loader.py` yaz:
  - AGENT + SKILL parse,
  - runtime cache,
  - version hash.

### Faz 1 (2-3 gün) - Skill Runtime
- Skill registry tablosu:
  - `skill_id`, `version`, `enabled`, `risk_level`, `owner`.
- Skill execution pipeline:
  - pre-check (permissions/rate limits),
  - execute,
  - post-check (quality + policy).
- Skill bazlı observability:
  - latency, success rate, error class, approval rate.

### Faz 2 (3-4 gün) - Memory v2 (Hybrid)
- Yeni tablolar:
  - `memory_events` (ham olay),
  - `memory_facts` (çıkarılan bilgi),
  - `memory_compactions` (compile çıktısı),
  - `memory_links` (olay <-> fakt ilişkisi).
- Compile işleri:
  - saatlik micro-compile (son 1 saat),
  - günlük compile (özet + öğrenim),
  - haftalık strategy compile (KPI + experiment learnings).
- Retrieval sırası:
  - önce L3/L4,
  - yetmezse L2,
  - en son L1.

### Faz 3 (2-3 gün) - OpenClaw-Compatible Control Plane
- Var olan `/v1/chat/completions` endpoint’i üstüne:
  - `GET /agent/state`,
  - `GET /skills`,
  - `POST /skills/{id}/enable|disable`,
  - `GET /memory/summary`.
- UI/Panel:
  - aktif policy,
  - skill toggles,
  - running jobs,
  - recent memory compiles.

### Faz 4 (2 gün) - Approval ve Safety
- Risk matrisi:
  - low: auto,
  - medium: rule-based gate,
  - high: human approval.
- Outbox + skill seviyesi policy enforcement:
  - "direct write forbidden" kuralı skill runtime’a da uygulanır.

### Faz 5 (2 gün) - Evaluation
- Benchmark set:
  - 20 standart görev,
  - 10 yüksek risk görev,
  - 10 growth experiment görev.
- Kabul kriterleri:
  - task success >= %85,
  - policy ihlali = 0,
  - duplicate publish/reply = 0,
  - compile sonrası retrieval latency düşüşü >= %30.

## 5) Sprint Çıktısı (Öneri: 2 hafta)
- Week 1:
  - Faz 0 + Faz 1 + Faz 2'nin yarısı.
- Week 2:
  - Faz 2 tamam + Faz 3 + Faz 4 + Faz 5 smoke.

## 6) İlk Uygulanacak 5 İş
1. `agent/AGENT.md` şablonunu oluştur.
2. `skills/core-content/SKILL.md` ve `skills/community/SKILL.md` ilk iki skill'i yaz.
3. `agent_contract_loader.py` + unit test.
4. `memory_events` / `memory_compactions` migration'larını ekle.
5. Saatlik compile Celery task'ını yaz (`run_memory_compile_hourly`).

