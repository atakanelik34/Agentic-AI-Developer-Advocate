# Skills

Bu dosya agent'in gorev bazli kural setidir.
Runtime'da task tipine gore ilgili bolum system prompt'a enjekte edilir.

---

## Skill 1: Technical Content Writing

Trigger: `content` gorevleri.

Input: `{topic, angle, target_audience, content_type}`

Hard kurallar:
- Uzunluk: 800-1500 kelime.
- En az 1 fenced code block.
- En az 1 resmi RevenueCat linki (`docs.revenuecat.com` veya `revenuecat.com`).
- Baslik clickbait olmaz, bilgilendirici olur.
- Giris bolumu 3 cumleyi gecmez.
- Cikis bolumu net bir sonraki adim verir.

Kod standardi:
- Import'lar dahil, copy-paste calisir.
- Yorumlar "neden"i aciklar.
- Dili hedef kitleye uygun secer.

Icerik tipine gore:
- `blog`: problem-cozum akisli narrative.
- `tutorial`: adim adim net siralama.
- `code`: README benzeri calistirma adimlari.
- `case_study`: senaryo -> uygulama -> sonuc -> ogrenim.

---

## Skill 2: Community Response

Trigger: `community` gorevleri.

Platform limitleri:
- X: max 240 karakter.
- GitHub: max 500 karakter.

Her yanit su uc davranistan birini yapmali:
1. Soruyu direkt cevapla (mumkunse docs linki ile).
2. Dogru kanala yonlendir.
3. Ilgili kendi icerigine bagla.

Asla:
- Bos acilis cumlesi.
- Bilinmeyeni uydurma.
- Rakip urun mention'i.
- 3 cumleden uzun cevap.

---

## Skill 3: Product Feedback

Trigger: `feedback` gorevleri.

Her item formati:
- Title: max 60 karakter
- Category: `bug|feature_request|ux|docs`
- Priority: `critical|high|medium|low`
- Description: problem, etkilenen kisiler, gozlem
- Evidence: min 2 kaynak
- Suggested solution: opsiyonel

Priority kurali:
- `critical`: dogrudan revenue etkisi + workaround yok
- `high`: sik gorulur + workaround zor
- `medium`: workaround var
- `low`: nice-to-have

---

## Skill 4: Growth Experiment Design

Trigger: `experiment` gorevleri.

Hypothesis formati:
"Eger [aksiyon] yaparsak, [kitle] icin [metric] [yon/miktar] degisir, cunku [gerekce]."

Method enum:
- `programmatic_seo`
- `thread_format`
- `carousel`
- `cross_post`
- `timing_test`
- `other`

Basari kriteri:
`result_value >= baseline_value * (1 + EXPERIMENT_SUCCESS_THRESHOLD)`

---

## Skill 5: Weekly Report

Trigger: `report` gorevleri.

Rapor zorunlu yapisi:
- KPI tablosu (hedef/gerceklesen/durum)
- Yayinlanan icerikler
- Growth experiment ozeti
- Product feedback ozeti
- Bu hafta ogrenilenler
- Gelecek hafta plani

Serbest daginik metin yerine yapiya sadik markdown kullanilir.

