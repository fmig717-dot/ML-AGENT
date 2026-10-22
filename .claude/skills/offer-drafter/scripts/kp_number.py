"""
Выдаёт номер волны и номер КП по формату из rules.md:
    PRODUCT/yymm-dd_WAVE   (пример: CFA/2610-22_04)

Состояние (последний номер волны на каждый продукт) хранится в
output/kp_state.json, чтобы номера не повторялись и не терялись между запусками.

Использование:
    python3 kp_number.py peek   <PRODUCT> [--date YYYY-MM-DD]
    python3 kp_number.py commit <PRODUCT> [--date YYYY-MM-DD]

- peek   — показать, какой будет СЛЕДУЮЩИЙ номер волны/КП, НЕ сохраняя изменений.
           Используй это, чтобы показать пользователю номер до подтверждения волны
           (правило 7 — сначала подтверждение, потом создание драфтов).
- commit — реально увеличить счётчик волны для продукта и сохранить номер. Вызывай
           это ТОЛЬКО после того, как пользователь подтвердил волну — иначе номера
           будут "сгорать" впустую при отменённых волнах.

Без --date используется сегодняшняя дата по системным часам.
"""
import json
import os
import sys
from datetime import date

STATE_PATH = os.path.join("output", "kp_state.json")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def format_kp(product, d, wave):
    yy = d.strftime("%y")
    mm = d.strftime("%m")
    dd = d.strftime("%d")
    return f"{product}/{yy}{mm}-{dd}_{wave:02d}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    product = sys.argv[2]

    run_date = date.today()
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        run_date = date.fromisoformat(sys.argv[idx + 1])

    if mode not in ("peek", "commit"):
        print(f"Неизвестный режим '{mode}'. Используй 'peek' или 'commit'.")
        sys.exit(1)

    state = load_state()
    last_wave = state.get(product, {}).get("last_wave", 0)
    next_wave = last_wave + 1

    kp_number = format_kp(product, run_date, next_wave)

    if mode == "peek":
        print(json.dumps({
            "mode": "peek",
            "product": product,
            "wave": next_wave,
            "kp_number": kp_number,
            "note": "Номер НЕ зафиксирован. Запусти 'commit' после подтверждения волны пользователем.",
        }, ensure_ascii=False, indent=2))
    else:
        state[product] = {"last_wave": next_wave, "last_kp_number": kp_number, "last_date": run_date.isoformat()}
        save_state(state)
        print(json.dumps({
            "mode": "commit",
            "product": product,
            "wave": next_wave,
            "kp_number": kp_number,
            "note": "Номер зафиксирован и сохранён в output/kp_state.json.",
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
