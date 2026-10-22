# Шаблон письма — Soft Commercial Offer

Заполняй плейсхолдеры `[...]` под конкретную компанию из buyers.xlsx (используй её
`fit_reasoning` и `notes`, чтобы 1-2 фразы были персонализированы, а не шаблонны под
копирку). **Никаких конкретных календарных дат в тексте** (правило 4 из `rules.md`).

## Тема письма

**Персонализируется под каждую компанию — не повторяется одинаково внутри волны**
(правило 8 rules.md). Обязательно содержит название компании и короткое понятное имя
продукта, не только номер КП:

```
Soft Commercial Offer — [Product short name] for [Company] — Ref. [KP_NUMBER]
```

Пример: `Soft Commercial Offer — Cotton Soapstock Fatty Acids for Agrioil — Ref. CFA/2610-22_01`
(не просто "CFA" — в теме по возможности расшифровать продукт, чтобы было понятно без
открытия письма).

## Тело письма (HTML, `htmlBody`)

```html
<p>Dear [Contact person or "Team" / "Sir or Madam" if contact_person не найден],</p>

<p>My name is Fadei Migalcian, I represent the Trading Department of FITO VITA SRL.
We are currently offering [Product short description] and believe it may be a good
fit for [Company name], given [1-2 фразы на основе fit_reasoning этой компании].</p>

<p>This is a soft commercial offer (Ref. [KP_NUMBER]) — we would be glad to start a
dialogue and share further details (technical specification, certificate of conformity,
lab analysis, trial shipment terms) upon your interest.</p>

<p>[1 фраза адаптированная из notes компании — например про MOQ, пробную партию,
особенности логистики — без конкретных дат].</p>

<p>This offer is valid for 14 days from the date of issue indicated in its reference
number.</p>

<p>Looking forward to your reply.</p>

<!-- вставь сюда HTML-подпись из templates/signature_html.md -->
```

## Тело письма (plain text, `body` — обязательно заполнить как альтернативу)

Та же структура без HTML-тегов, оканчивается plain-text подписью из
`templates/signature_html.md`.

## Что подставить

| Плейсхолдер | Источник |
|---|---|
| `[Product]` / `[Product short description]` | продукт волны (поле `product` в buyers.xlsx) |
| `[KP_NUMBER]` | номер КП, выданный `scripts/kp_number.py` на эту волну |
| `[Contact person ...]` | поле `contact_person` компании; если "не найдено" — нейтральное обращение |
| `[Company name]` | поле `company` |
| `fit_reasoning этой компании` | поле `fit_reasoning` из buyers.xlsx/buyers.json |
| `notes компании` | поле `notes` из buyers.xlsx/buyers.json |

Вложения по умолчанию НЕ прикладываются и НЕ упоминаются как "attached" (rules.md §5,
решение пользователя от 22.10.2026) — письмо предлагает "share further details upon your
interest" без обещания конкретных файлов. Если пользователь явно попросит вложить файлы в
конкретную волну — тогда прикладывай ровно то, что в `attachments/<product>/manifest.json`,
и допиши в письмо реальный список того, что приложено.

Не добавляй цену/жёсткие условия в текст — это именно soft offer (правило 2).
