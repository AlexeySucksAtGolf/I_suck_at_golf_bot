# I_suck_at_golf — Telegram bot
# python-telegram-bot==21.3

from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from dataclasses import dataclass, field, asdict
from collections import defaultdict, Counter
from datetime import datetime
import csv, io, uuid

# ====== НАСТРОЙКИ ======
TOKEN = "8280360970:AAGvux9EoEPrMYjT5bTeSTOyZ26dW1ooBIQ"  # <-- ВСТАВЬ СВОЙ ТОКЕН

BOT_NAME = "I_suck_at_golf"

# Emoji / labels
ARW_UP, ARW_DOWN, ARW_RIGHT, ARW_LEFT = "⬆️", "⬇️", "➡️", "⬅️"
CHECK, CROSS, BACK, CANCEL, CONFIRM = "✅", "❌", "⬅ Back", "✖ Cancel", "✅ Confirm"

# Choices
LIES = ["tee", "fairway", "rough", "deep rough", "fringe", "green", "sand", "mat", "bare lie", "divot"]

CLUBS = ["Dr", "3w", "5w", "7w", "3h", "3", "4", "5", "6", "7", "8", "9",
         "GW", "PW", "SW", "LW", "54", "56", "58", "60", "Putter"]

SHOT_TYPES = [
    "full swing", "3/4", "half swing",
    "pitch shot", "bunker shot", "chip shot",
    "bump and run", "flop shot", "putt"
]

RESULT_NON_PUTT = [ARW_UP, ARW_DOWN, ARW_RIGHT, ARW_LEFT, f"{CHECK}"]
CONTACT_NON_PUTT = ["thin", "fat", "toe", "heel", "shank", "high on face", "low on face", f"good {CHECK}"]
PLAN_CHOICES = [f"shot as planned {CHECK}", f"not as planned {CROSS}"]

# Putt branch
PUTT_DISTANCE = ["Long putt", "Short putt"]
RESULT_PUTT = [ARW_UP, ARW_DOWN, ARW_RIGHT, ARW_LEFT, f"{CHECK}"]
CONTACT_PUTT = ["toe", "heel", f"good {CHECK}"]
LAG_PUTT = ["good reading", "poor reading"]

# Control buttons shown on step keyboards
CTRL_BACK = [BACK]
CTRL_CONFIRM_CANCEL = [[CONFIRM, CANCEL]]
CTRL_BACK_ROW = [[BACK]]

# ====== ДАННЫЕ ======
@dataclass
class Shot:
    timestamp: str
    mode: str  # "practice" or "oncourse"
    session_id: str
    hole: int | None = None

    # sticky for practice; explicit for round
    lie: str | None = None
    club: str | None = None

    shot_type: str | None = None

    # non-putt path
    result: str | None = None
    contact: str | None = None
    plan: str | None = None

    # putt path
    putt_distance: str | None = None
    putt_result: str | None = None
    putt_contact: str | None = None
    putt_plan_1: str | None = None
    lag_reading: str | None = None
    putt_plan_2: str | None = None

    def as_row(self):
        """Flat row for raw CSV."""
        return [
            self.timestamp, self.mode, self.session_id, self.hole,
            self.lie, self.club, self.shot_type,
            self.result, self.contact, self.plan,
            self.putt_distance, self.putt_result, self.putt_contact,
            self.putt_plan_1, self.lag_reading, self.putt_plan_2
        ]

RAW_HEADER = [
    "timestamp","mode","session_id","hole",
    "lie","club","shot_type",
    "result","contact","plan",
    "putt_distance","putt_result","putt_contact",
    "putt_plan_1","lag_reading","putt_plan_2"
]

# ====== ВСПОМОГАТЕЛЬНОЕ ======
def kb(rows): return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def pct(a, b):
    return 0.0 if not b else round(a * 100.0 / b, 1)

def ensure_session(ctx: ContextTypes.DEFAULT_TYPE):
    if "core" not in ctx.user_data:
        ctx.user_data["core"] = {}
    core = ctx.user_data["core"]
    if "session_id" not in core:
        core["session_id"] = str(uuid.uuid4())
    if "mode" not in core:
        core["mode"] = None   # "practice" / "oncourse"
    if "shots" not in core:
        core["shots"] = []    # list[Shot]
    if "current" not in core:
        core["current"] = None  # Shot-building object
    if "stack" not in core:
        core["stack"] = []    # for back
    if "practice" not in core:
        core["practice"] = {"lie": None, "club": None}
    if "round" not in core:
        core["round"] = {"hole": 1}
    return core

def start_new_shot(core, putt: bool=False):
    s = Shot(timestamp=now_iso(), mode=core["mode"], session_id=core["session_id"])
    if core["mode"] == "oncourse":
        s.hole = core["round"]["hole"]
    if core["mode"] == "practice":
        # apply sticky
        s.lie = core["practice"]["lie"]
        s.club = core["practice"]["club"]
    core["current"] = s
    core["stack"] = []  # reset back stack

def push_state(core):
    # save a shallow copy for back
    snap = asdict(core["current"])
    core["stack"].append(snap)

def pop_state(core):
    if core["stack"]:
        prev = core["stack"].pop()
        s = Shot(**prev)
        core["current"] = s
        return True
    return False

def summarize_shot(s: Shot) -> str:
    lines = []
    lines.append(f"Mode: {s.mode}")
    if s.hole: lines.append(f"Hole: {s.hole}")
    if s.lie: lines.append(f"Lie: {s.lie}")
    if s.club: lines.append(f"Club: {s.club}")
    if s.shot_type: lines.append(f"Type: {s.shot_type}")

    if s.shot_type == "putt":
        if s.putt_distance: lines.append(f"Distance: {s.putt_distance}")
        if s.putt_result: lines.append(f"Result: {s.putt_result}")
        if s.putt_contact: lines.append(f"Contact: {s.putt_contact}")
        if s.putt_plan_1: lines.append(f"Plan #1: {s.putt_plan_1}")
        if s.lag_reading: lines.append(f"Lag: {s.lag_reading}")
        if s.putt_plan_2: lines.append(f"Plan #2: {s.putt_plan_2}")
    else:
        if s.result: lines.append(f"Result: {s.result}")
        if s.contact: lines.append(f"Contact: {s.contact}")
        if s.plan: lines.append(f"Plan: {s.plan}")

    return "\n".join(lines)

def club_basename(c: str) -> str:
    # unify putter naming etc. Here we keep as-is.
    return c or "—"

# ====== КЛАВИАТУРЫ ПО ШАГАМ ======
def step_keyboard_step1_mode():
    return kb([["practice", "on course"]])

def step_keyboard_lie():
    rows = [LIES[i:i+3] for i in range(0, len(LIES), 3)]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_club():
    rows = [CLUBS[i:i+5] for i in range(0, len(CLUBS), 5)]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_type():
    rows = [SHOT_TYPES[i:i+3] for i in range(0, len(SHOT_TYPES), 3)]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_result(is_putt=False):
    choices = RESULT_PUTT if is_putt else RESULT_NON_PUTT
    rows = [choices[i:i+3] for i in range(0, len(choices), 3)]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_contact(is_putt=False):
    choices = CONTACT_PUTT if is_putt else CONTACT_NON_PUTT
    rows = [choices[i:i+3] for i in range(0, len(choices), 3)]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_plan():
    rows = [PLAN_CHOICES]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_putt_distance():
    rows = [PUTT_DISTANCE]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_lag_putt():
    rows = [LAG_PUTT]
    rows += CTRL_BACK_ROW
    return kb(rows)

def step_keyboard_confirm():
    return kb([[CONFIRM, CANCEL], [BACK]])

# ====== ЛОГИКА ШАГОВ ======
async def ask_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hi, this is **{BOT_NAME}**.\nChoose mode:",
        reply_markup=step_keyboard_step1_mode()
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    await ask_mode(update, context)

async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    text = update.message.text

    if text not in ["practice", "on course"]:
        return await update.message.reply_text("Choose mode:", reply_markup=step_keyboard_step1_mode())

    core["mode"] = text
    core["session_id"] = str(uuid.uuid4())
    core["shots"] = []
    core["current"] = None
    core["stack"] = []

    if text == "practice":
        core["practice"] = {"lie": None, "club": None}
        await update.message.reply_text("Practice mode selected.\nPick Lie:", reply_markup=step_keyboard_lie())
    else:
        core["round"] = {"hole": 1}
        await update.message.reply_text("On-course mode selected.\nHole = 1.\nStart a shot with /shot\nUse /next_hole to advance hole.",
                                        reply_markup=ReplyKeyboardRemove())

# ========== PRACTICE: sticky lie/club ==========
async def handle_practice_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    if core["mode"] != "practice":
        return

    text = update.message.text

    # set lie
    if core["practice"]["lie"] is None:
        if text == BACK:
            return await ask_mode(update, context)
        if text in LIES:
            core["practice"]["lie"] = text
            return await update.message.reply_text(f"Lie: {text}\nNow pick Club:", reply_markup=step_keyboard_club())
        else:
            return await update.message.reply_text("Pick Lie:", reply_markup=step_keyboard_lie())

    # set club
    if core["practice"]["club"] is None:
        if text == BACK:
            core["practice"]["lie"] = None
            return await update.message.reply_text("Pick Lie:", reply_markup=step_keyboard_lie())
        if text in CLUBS:
            core["practice"]["club"] = text
            # ready to log shots quickly
            start_new_shot(core)  # prefill with sticky values
            return await update.message.reply_text(
                f"Sticky set ✅\nLie: {core['practice']['lie']} | Club: {core['practice']['club']}\nStart a shot: choose Type",
                reply_markup=step_keyboard_type()
            )
        else:
            return await update.message.reply_text("Pick Club:", reply_markup=step_keyboard_club())

    # if both set, proceed into shot flow
    await shot_flow(update, context)

# ========== ON-COURSE commands ==========
async def cmd_shot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    if core["mode"] != "on course":
        return await update.message.reply_text("You are not in on-course mode. Use /start to switch.")

    start_new_shot(core)
    await update.message.reply_text(f"Hole {core['round']['hole']}: choose Type of shot", reply_markup=step_keyboard_type())

async def cmd_next_hole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    if core["mode"] != "on course":
        return await update.message.reply_text("You are not in on-course mode.")
    core["round"]["hole"] += 1
    await update.message.reply_text(f"Moved to hole {core['round']['hole']}. Add a shot: /shot")

# ========== COMMON SHOT FLOW (both modes) ==========
async def shot_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    s: Shot | None = core["current"]
    if s is None:
        # In practice: if sticky set, start new shot; otherwise we are still setting sticky
        if core["mode"] == "practice":
            if core["practice"]["lie"] and core["practice"]["club"]:
                start_new_shot(core)
                s = core["current"]
            else:
                return  # still in setup handler
        else:
            return await update.message.reply_text("Start a shot with /shot")

    text = update.message.text

    # Back on any step
    if text == BACK:
        if pop_state(core):
            # re-ask appropriate step
            return await ask_next_step(update, core["current"])
        else:
            return await update.message.reply_text("Nothing to go back to.")

    # Cancel shot
    if text == CANCEL:
        core["current"] = None
        core["stack"] = []
        msg = "Shot canceled."
        if core["mode"] == "practice":
            msg += "\nStart new shot: choose Type."
            return await update.message.reply_text(msg, reply_markup=step_keyboard_type())
        else:
            msg += "\nStart new on-course shot: /shot"
            return await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())

    # Confirm shot
    if text == CONFIRM:
        # must be after full path
        core["shots"].append(core["current"])
        core["current"] = None
        core["stack"] = []
        if core["mode"] == "practice":
            # Start next quickly with sticky
            start_new_shot(core)
            return await update.message.reply_text("Saved ✅\nNew shot: choose Type", reply_markup=step_keyboard_type())
        else:
            return await update.message.reply_text("Saved ✅\nAdd next: /shot", reply_markup=ReplyKeyboardRemove())

    # Progression
    # 1) Type
    if s.shot_type is None:
        if text in SHOT_TYPES:
            push_state(core)
            s.shot_type = text
            # In on-course, ask lie/club explicitly; in practice already set
            if s.shot_type == "putt":
                return await update.message.reply_text("Distance?", reply_markup=step_keyboard_putt_distance())
            else:
                # For both modes we continue standard path; but ensure lie/club known
                if s.lie is None:
                    return await update.message.reply_text("Lie?", reply_markup=step_keyboard_lie())
                if s.club is None:
                    return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())
                return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=False))
        else:
            return await update.message.reply_text("Choose Type:", reply_markup=step_keyboard_type())

    # If non-putt path
    if s.shot_type != "putt":
        # Ensure lie
        if s.lie is None:
            if text in LIES:
                push_state(core)
                s.lie = text
                return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())
            else:
                return await update.message.reply_text("Lie?", reply_markup=step_keyboard_lie())
        # Ensure club
        if s.club is None:
            if text in CLUBS:
                push_state(core)
                s.club = text
                return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=False))
            else:
                return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())

        # Result
        if s.result is None:
            if text in RESULT_NON_PUTT:
                push_state(core)
                s.result = text
                return await update.message.reply_text("Contact?", reply_markup=step_keyboard_contact(is_putt=False))
            else:
                return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=False))

        # Contact
        if s.contact is None:
            if text in CONTACT_NON_PUTT:
                push_state(core)
                s.contact = text
                return await update.message.reply_text("Plan?", reply_markup=step_keyboard_plan())
            else:
                return await update.message.reply_text("Contact?", reply_markup=step_keyboard_contact(is_putt=False))

        # Plan
        if s.plan is None:
            if text in PLAN_CHOICES:
                push_state(core)
                s.plan = text
                # Confirm
                summary = summarize_shot(s)
                return await update.message.reply_text(f"Review:\n{summary}", reply_markup=step_keyboard_confirm())
            else:
                return await update.message.reply_text("Plan?", reply_markup=step_keyboard_plan())

    # PUTT path
    else:
        if s.putt_distance is None:
            if text in PUTT_DISTANCE:
                push_state(core)
                s.putt_distance = text
                # Putt: ensure lie/club for completeness
                if s.lie is None:
                    return await update.message.reply_text("Lie?", reply_markup=step_keyboard_lie())
                if s.club is None:
                    return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())
                return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=True))
            else:
                return await update.message.reply_text("Distance?", reply_markup=step_keyboard_putt_distance())

        if s.lie is None:
            if text in LIES:
                push_state(core)
                s.lie = text
                return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())
            else:
                return await update.message.reply_text("Lie?", reply_markup=step_keyboard_lie())

        if s.club is None:
            if text in CLUBS:
                push_state(core)
                s.club = text
                return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=True))
            else:
                return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())

        if s.putt_result is None:
            if text in RESULT_PUTT:
                push_state(core)
                s.putt_result = text
                return await update.message.reply_text("Contact?", reply_markup=step_keyboard_contact(is_putt=True))
            else:
                return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=True))

        if s.putt_contact is None:
            if text in CONTACT_PUTT:
                push_state(core)
                s.putt_contact = text
                return await update.message.reply_text("Plan?", reply_markup=step_keyboard_plan())
            else:
                return await update.message.reply_text("Contact?", reply_markup=step_keyboard_contact(is_putt=True))

        if s.putt_plan_1 is None:
            if text in PLAN_CHOICES:
                push_state(core)
                s.putt_plan_1 = text
                return await update.message.reply_text("Lag putt reading?", reply_markup=step_keyboard_lag_putt())
            else:
                return await update.message.reply_text("Plan?", reply_markup=step_keyboard_plan())

        if s.lag_reading is None:
            if text in LAG_PUTT:
                push_state(core)
                s.lag_reading = text
                return await update.message.reply_text("Plan (after lag)?", reply_markup=step_keyboard_plan())
            else:
                return await update.message.reply_text("Lag putt reading?", reply_markup=step_keyboard_lag_putt())

        if s.putt_plan_2 is None:
            if text in PLAN_CHOICES:
                push_state(core)
                s.putt_plan_2 = text
                summary = summarize_shot(s)
                return await update.message.reply_text(f"Review:\n{summary}", reply_markup=step_keyboard_confirm())
            else:
                return await update.message.reply_text("Plan (after lag)?", reply_markup=step_keyboard_plan())

# ====== СТАТИСТИКА (в процентах по каждой клюшке за СЕССИЮ) ======
def compute_stats_by_club(shots: list[Shot]):
    # группируем по клюшке
    by_club = defaultdict(list)
    for s in shots:
        c = club_basename(s.club)
        by_club[c].append(s)

    # готовим таблицу: Club, N, затем проценты по Result, Contact, Plan
    # фиксируем универсальные списки ключей (пустые значения игнорируем)
    result_keys = list(dict.fromkeys(RESULT_NON_PUTT + RESULT_PUTT))
    contact_keys = list(dict.fromkeys([*CONTACT_NON_PUTT, *CONTACT_PUTT]))
    plan_keys = PLAN_CHOICES
    lag_keys = LAG_PUTT  # только для паттов

    rows = []
    header = ["Club", "n"]
    header += [f"Result % {k}" for k in result_keys]
    header += [f"Contact % {k}" for k in contact_keys]
    header += [f"Plan % {k}" for k in plan_keys]
    header += [f"Lag % {k}" for k in lag_keys]  # будет 0% для не-паттов
    rows.append(header)

    for club, lst in by_club.items():
        N = len(lst)
        # собираем плоские значения
        res = []
        con = []
        plan = []
        lag = []
        for s in lst:
            if s.shot_type == "putt":
                if s.putt_result: res.append(s.putt_result)
                if s.putt_contact: con.append(s.putt_contact)
                if s.putt_plan_1: plan.append(s.putt_plan_1)
                if s.putt_plan_2: plan.append(s.putt_plan_2)
                if s.lag_reading: lag.append(s.lag_reading)
            else:
                if s.result: res.append(s.result)
                if s.contact: con.append(s.contact)
                if s.plan: plan.append(s.plan)

        rc = Counter(res)
        cc = Counter(con)
        pc = Counter(plan)
        lc = Counter(lag)

        row = [club, N]
        row += [pct(rc.get(k, 0), N) for k in result_keys]
        row += [pct(cc.get(k, 0), N) for k in contact_keys]
        row += [pct(pc.get(k, 0), N) for k in plan_keys]
        row += [pct(lc.get(k, 0), N) for k in lag_keys]
        rows.append(row)
    return rows

def csv_bytes_from_rows(rows: list[list]):
    buf = io.StringIO()
    writer = csv.writer(buf)
    for r in rows:
        writer.writerow(r)
    return io.BytesIO(buf.getvalue().encode("utf-8"))

def raw_csv_bytes(shots: list[Shot]):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(RAW_HEADER)
    for s in shots:
        w.writerow(s.as_row())
    return io.BytesIO(buf.getvalue().encode("utf-8"))

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    if not core["shots"]:
        return await update.message.reply_text("No shots yet in this session.")
    rows = compute_stats_by_club(core["shots"])
    stats_file = csv_bytes_from_rows(rows)
    raw_file = raw_csv_bytes(core["shots"])

    stats_file.name = "stats_by_club.csv"
    raw_file.name = "raw_shots.csv"

    await update.message.reply_text(
        "Statistics are percentages per club within the current session."
        "\nI’m sending two CSVs ready for Google Sheets:"
        "\n• stats_by_club.csv — percentages"
        "\n• raw_shots.csv — raw log"
    )
    await update.message.reply_document(InputFile(stats_file))
    await update.message.reply_document(InputFile(raw_file))

# ====== ХЭНДЛЕРЫ ======
async def any_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    core = ensure_session(context)
    # route by mode and phase
    if core["mode"] is None:
        return await handle_mode(update, context)

    if core["mode"] == "practice":
        # If still setting sticky lie/club
        if core["practice"]["lie"] is None or core["practice"]["club"] is None:
            return await handle_practice_setup(update, context)
        # Else — in-shot flow
        return await shot_flow(update, context)

    if core["mode"] == "on course":
        # only /shot starts a shot; otherwise flow continues
        return await shot_flow(update, context)

async def ask_next_step(update: Update, s: Shot):
    # re-ask appropriate step after Back
    if s.shot_type is None:
        return await update.message.reply_text("Choose Type:", reply_markup=step_keyboard_type())

    if s.shot_type != "putt":
        if s.lie is None:
            return await update.message.reply_text("Lie?", reply_markup=step_keyboard_lie())
        if s.club is None:
            return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())
        if s.result is None:
            return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=False))
        if s.contact is None:
            return await update.message.reply_text("Contact?", reply_markup=step_keyboard_contact(is_putt=False))
        if s.plan is None:
            return await update.message.reply_text("Plan?", reply_markup=step_keyboard_plan())
        return await update.message.reply_text(f"Review:\n{summarize_shot(s)}", reply_markup=step_keyboard_confirm())

    else:
        if s.putt_distance is None:
            return await update.message.reply_text("Distance?", reply_markup=step_keyboard_putt_distance())
        if s.lie is None:
            return await update.message.reply_text("Lie?", reply_markup=step_keyboard_lie())
        if s.club is None:
            return await update.message.reply_text("Club?", reply_markup=step_keyboard_club())
        if s.putt_result is None:
            return await update.message.reply_text("Result?", reply_markup=step_keyboard_result(is_putt=True))
        if s.putt_contact is None:
            return await update.message.reply_text("Contact?", reply_markup=step_keyboard_contact(is_putt=True))
        if s.putt_plan_1 is None:
            return await update.message.reply_text("Plan?", reply_markup=step_keyboard_plan())
        if s.lag_reading is None:
            return await update.message.reply_text("Lag putt reading?", reply_markup=step_keyboard_lag_putt())
        if s.putt_plan_2 is None:
            return await update.message.reply_text("Plan (after lag)?", reply_markup=step_keyboard_plan())
        return await update.message.reply_text(f"Review:\n{summarize_shot(s)}", reply_markup=step_keyboard_confirm())

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("shot", cmd_shot))
    app.add_handler(CommandHandler("next_hole", cmd_next_hole))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_text))
    app.run_polling()

if __name__ == "__main__":
    main()
