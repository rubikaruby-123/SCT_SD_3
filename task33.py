import customtkinter as ctk
import numpy as np
import random
import json
import os
import copy
from datetime import date
import tkinter.messagebox as messagebox

# ─────────────────────────────────────────────
#  App Setup
# ─────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

app = ctk.CTk()
app.title("Sudoku")
app.geometry("780x980")
app.resizable(False, False)

# ─────────────────────────────────────────────
#  Background Canvas
# ─────────────────────────────────────────────
canvas = ctk.CTkCanvas(app, width=780, height=980)
canvas.pack(fill="both", expand=True)

def draw_gradient(canvas, color_top="#EDEA0B", color_bottom="#232020"):
    for i in range(980):
        ratio = i / 980
        r1, g1, b1 = app.winfo_rgb(color_top)
        r2, g2, b2 = app.winfo_rgb(color_bottom)
        r = int(r1 + (r2 - r1) * ratio) >> 8
        g = int(g1 + (g2 - g1) * ratio) >> 8
        b = int(b1 + (b2 - b1) * ratio) >> 8
        canvas.create_line(0, i, 780, i, fill=f"#{r:02x}{g:02x}{b:02x}")

draw_gradient(canvas)

# ─────────────────────────────────────────────
#  Main Frame
# ─────────────────────────────────────────────
frame = ctk.CTkFrame(canvas, fg_color="transparent")
frame.place(relx=0.5, rely=0.0, anchor="n")

# Title
ctk.CTkLabel(frame, text="Sudoku", font=("Arial", 32, "bold"), text_color="black").pack(pady=(14, 2))

# ─────────────────────────────────────────────
#  Game State
# ─────────────────────────────────────────────
grid_frame      = None
entries         = []
current_grid_size = 9
solution_board  = []          # full solved board for hints / mistake checking
given_cells     = set()       # (r, c) cells that are pre-filled (read-only)
mistakes        = 0
MAX_MISTAKES    = 3
is_paused       = False
game_over_flag  = False

# Undo / Redo stacks – each item: (row, col, old_val, new_val)
undo_stack = []
redo_stack = []

# Timer
timer_seconds   = 0
timer_running   = False
timer_job       = None

SAVE_FILE = "sudoku_save.json"

# ─────────────────────────────────────────────
#  Top Info Bar  (timer | mistakes | pause)
# ─────────────────────────────────────────────
info_frame = ctk.CTkFrame(frame, fg_color="transparent")
info_frame.pack(fill="x", padx=10, pady=(0, 4))

timer_label = ctk.CTkLabel(info_frame, text="⏱ 00:00", font=("Arial", 15, "bold"), text_color="black")
timer_label.pack(side="left", padx=10)

mistakes_label = ctk.CTkLabel(info_frame, text="❌ Mistakes: 0/3", font=("Arial", 15, "bold"), text_color="black")
mistakes_label.pack(side="left", padx=10)

# ─────────────────────────────────────────────
#  Timer Logic
# ─────────────────────────────────────────────
def update_timer():
    global timer_seconds, timer_job
    if timer_running and not is_paused:
        timer_seconds += 1
        m, s = divmod(timer_seconds, 60)
        timer_label.configure(text=f"⏱ {m:02d}:{s:02d}")
    timer_job = app.after(1000, update_timer)

def start_timer():
    global timer_running
    timer_running = True

def stop_timer():
    global timer_running
    timer_running = False

def reset_timer():
    global timer_seconds
    timer_seconds = 0
    timer_label.configure(text="⏱ 00:00")

# ─────────────────────────────────────────────
#  Sudoku Generator
# ─────────────────────────────────────────────
def generate_full_board(size=9):
    board = [[0]*size for _ in range(size)]
    fill_board(board, size)
    return board

def fill_board(board, size):
    block = int(np.sqrt(size))
    for r in range(size):
        for c in range(size):
            if board[r][c] == 0:
                nums = list(range(1, size+1))
                random.shuffle(nums)
                for num in nums:
                    if is_valid(board, r, c, num, size, block):
                        board[r][c] = num
                        if fill_board(board, size):
                            return True
                        board[r][c] = 0
                return False
    return True

def is_valid(board, row, col, num, size, block):
    if num in board[row]:
        return False
    if num in [board[r][col] for r in range(size)]:
        return False
    sr, sc = block*(row//block), block*(col//block)
    for r in range(sr, sr+block):
        for c in range(sc, sc+block):
            if board[r][c] == num:
                return False
    return True

def remove_cells(full_board, difficulty, size=9):
    difficulty_map = {"Easy": 36, "Medium": 46, "Hard": 52, "Expert": 58}
    remove_count = difficulty_map.get(difficulty, 46)
    board = copy.deepcopy(full_board)
    removed = 0
    cells = [(r, c) for r in range(size) for c in range(size)]
    random.shuffle(cells)
    for r, c in cells:
        if removed >= remove_count:
            break
        backup = board[r][c]
        board[r][c] = 0
        removed += 1
        # optional: uniqueness check skipped for speed – good enough for gameplay
    return board

# ─────────────────────────────────────────────
#  Backtrack Solver
# ─────────────────────────────────────────────
def backtrack_solve(board):
    size = len(board)
    block = int(np.sqrt(size))
    for r in range(size):
        for c in range(size):
            if board[r][c] == 0:
                for num in range(1, size+1):
                    if is_valid(board, r, c, num, size, block):
                        board[r][c] = num
                        if backtrack_solve(board):
                            return True
                        board[r][c] = 0
                return False
    return True

# ─────────────────────────────────────────────
#  Grid Creation
# ─────────────────────────────────────────────
grid_sizes = {"4x4": 4, "9x9": 9, "16x16": 16}

def create_grid(size):
    global grid_frame, entries, current_grid_size
    current_grid_size = size
    if grid_frame:
        grid_frame.destroy()
    grid_frame = ctk.CTkFrame(frame, fg_color="#edf110", corner_radius=10)
    grid_frame.pack(pady=8)
    entries.clear()
    block = int(np.sqrt(size))
    for row in range(size):
        row_entries = []
        for col in range(size):
            e = ctk.CTkEntry(
                grid_frame,
                width=50 if size <= 9 else 36,
                height=50 if size <= 9 else 36,
                justify="center",
                font=("Arial", 18 if size == 9 else (14 if size == 4 else 11), "bold"),
                corner_radius=6,
                border_width=3 if (row % block == 0 or col % block == 0) else 1,
                border_color="#12EA19"
            )
            e.grid(
                row=row, column=col,
                padx=(3 if col % block == 0 else 1, 1),
                pady=(3 if row % block == 0 else 1, 1)
            )
            # Bind change tracking
            e.bind("<FocusOut>", lambda event, r=row, c=col: on_cell_change(r, c))
            e.bind("<Return>",   lambda event, r=row, c=col: on_cell_change(r, c))
            row_entries.append(e)
        entries.append(row_entries)

def set_cell(r, c, value, color="#FFFFFF"):
    e = entries[r][c]
    e.delete(0, "end")
    if value != 0:
        e.insert(0, str(value))
    e.configure(text_color=color)

def lock_given_cells():
    for (r, c) in given_cells:
        entries[r][c].configure(state="disabled", text_color="#FFD700", fg_color="#1a1a1a")

def unlock_all_cells():
    size = current_grid_size
    for r in range(size):
        for c in range(size):
            entries[r][c].configure(state="normal", text_color="#FFFFFF", fg_color=["#343638", "#1a1a1a"])

# ─────────────────────────────────────────────
#  Cell Change (mistake detection + undo)
# ─────────────────────────────────────────────
prev_values = {}  # (r,c) -> value before edit

def on_cell_focus_in(r, c):
    prev_values[(r, c)] = entries[r][c].get()

def on_cell_change(r, c):
    global mistakes
    if game_over_flag or is_paused:
        return
    if (r, c) in given_cells:
        return
    new_val = entries[r][c].get().strip()
    old_val = prev_values.get((r, c), "")
    if new_val == old_val:
        return
    prev_values[(r, c)] = new_val

    # Undo stack push
    undo_stack.append((r, c, old_val, new_val))
    redo_stack.clear()

    # Mistake check (only when a digit is entered)
    if new_val.isdigit() and solution_board:
        entered = int(new_val)
        correct = solution_board[r][c]
        if entered != correct:
            mistakes += 1
            mistakes_label.configure(text=f"❌ Mistakes: {mistakes}/{MAX_MISTAKES}")
            entries[r][c].configure(text_color="#FF4444")
            app.after(800, lambda: entries[r][c].configure(text_color="#FFFFFF"))
            if mistakes >= MAX_MISTAKES:
                game_over()
        else:
            entries[r][c].configure(text_color="#00FF88")

def game_over():
    global game_over_flag
    game_over_flag = True
    stop_timer()
    messagebox.showerror("Game Over", f"You made {MAX_MISTAKES} mistakes!\nGame over. Click 'New Game' to play again.")

# Bind focus-in AFTER grid creation
def rebind_cells():
    size = current_grid_size
    for r in range(size):
        for c in range(size):
            entries[r][c].bind("<FocusIn>", lambda event, rr=r, cc=c: on_cell_focus_in(rr, cc))

# ─────────────────────────────────────────────
#  Load Puzzle (static samples for 4 / 16)
# ─────────────────────────────────────────────
static_puzzles = {
    4: [
        [1, 0, 0, 4],
        [0, 0, 2, 0],
        [0, 3, 0, 0],
        [2, 0, 0, 3]
    ],
    16: [[0]*16 for _ in range(16)]
}

def load_puzzle():
    size = current_grid_size
    puzzle = static_puzzles.get(size)
    if puzzle is None:
        clear_board()
        return
    for r in range(size):
        for c in range(size):
            set_cell(r, c, puzzle[r][c])
    given_cells.clear()
    for r in range(size):
        for c in range(size):
            if puzzle[r][c] != 0:
                given_cells.add((r, c))
    lock_given_cells()

def clear_board():
    size = current_grid_size
    unlock_all_cells()
    for r in range(size):
        for c in range(size):
            entries[r][c].delete(0, "end")
    given_cells.clear()
    solution_board.clear()

def get_board():
    size = current_grid_size
    board = []
    for r in range(size):
        row = []
        for c in range(size):
            v = entries[r][c].get()
            row.append(int(v) if v.isdigit() else 0)
        board.append(row)
    return board

# ─────────────────────────────────────────────
#  New Game Generator
# ─────────────────────────────────────────────
def new_game(difficulty=None):
    global mistakes, game_over_flag
    if difficulty is None:
        difficulty = difficulty_var.get()
    size = current_grid_size
    if size != 9:
        messagebox.showinfo("Info", "New Game Generator works for 9×9.\nSwitching to 9×9.")
        size_choice.set("9x9")
        create_grid(9)

    reset_state()
    full = generate_full_board(9)
    solution_board.clear()
    solution_board.extend(copy.deepcopy(full))
    puzzle = remove_cells(full, difficulty, 9)
    given_cells.clear()
    unlock_all_cells()
    for r in range(9):
        for c in range(9):
            set_cell(r, c, puzzle[r][c])
            if puzzle[r][c] != 0:
                given_cells.add((r, c))
    lock_given_cells()
    rebind_cells()
    reset_timer()
    start_timer()
    game_over_flag = False
    mistakes_label.configure(text="❌ Mistakes: 0/3")

def reset_state():
    global mistakes
    mistakes = 0
    undo_stack.clear()
    redo_stack.clear()
    prev_values.clear()

# ─────────────────────────────────────────────
#  Daily Challenge
# ─────────────────────────────────────────────
def daily_challenge():
    global game_over_flag
    today = date.today()
    seed = today.year * 10000 + today.month * 100 + today.day
    random.seed(seed)
    full = generate_full_board(9)
    random.seed(None)  # restore randomness
    solution_board.clear()
    solution_board.extend(copy.deepcopy(full))
    puzzle = remove_cells(full, "Hard", 9)
    reset_state()
    given_cells.clear()
    unlock_all_cells()
    size_choice.set("9x9")
    create_grid(9)
    for r in range(9):
        for c in range(9):
            set_cell(r, c, puzzle[r][c])
            if puzzle[r][c] != 0:
                given_cells.add((r, c))
    lock_given_cells()
    rebind_cells()
    reset_timer()
    start_timer()
    game_over_flag = False
    mistakes_label.configure(text="❌ Mistakes: 0/3")
    messagebox.showinfo("Daily Challenge", f"Daily challenge for {today.strftime('%B %d, %Y')} loaded!\nGood luck!")

# ─────────────────────────────────────────────
#  Hint
# ─────────────────────────────────────────────
def hint():
    if game_over_flag or is_paused:
        return
    if not solution_board:
        messagebox.showinfo("Hint", "No solution available. Use 'New Game' or 'Solve' first.")
        return
    size = current_grid_size
    empties = [(r, c) for r in range(size) for c in range(size)
               if entries[r][c].get() == "" and (r, c) not in given_cells]
    if not empties:
        messagebox.showinfo("Hint", "Board is already complete!")
        return
    r, c = random.choice(empties)
    val = solution_board[r][c]
    old_val = entries[r][c].get()
    set_cell(r, c, val, "#00BFFF")
    undo_stack.append((r, c, old_val, str(val)))
    redo_stack.clear()
    prev_values[(r, c)] = str(val)

# ─────────────────────────────────────────────
#  Undo / Redo
# ─────────────────────────────────────────────
def undo():
    if not undo_stack or is_paused:
        return
    r, c, old_val, new_val = undo_stack.pop()
    redo_stack.append((r, c, old_val, new_val))
    entries[r][c].delete(0, "end")
    entries[r][c].insert(0, old_val)
    prev_values[(r, c)] = old_val

def redo():
    if not redo_stack or is_paused:
        return
    r, c, old_val, new_val = redo_stack.pop()
    undo_stack.append((r, c, old_val, new_val))
    entries[r][c].delete(0, "end")
    entries[r][c].insert(0, new_val)
    prev_values[(r, c)] = new_val

# ─────────────────────────────────────────────
#  Pause / Resume
# ─────────────────────────────────────────────
def toggle_pause():
    global is_paused
    if game_over_flag:
        return
    is_paused = not is_paused
    size = current_grid_size
    if is_paused:
        pause_btn.configure(text="▶ Resume")
        for r in range(size):
            for c in range(size):
                entries[r][c].configure(state="disabled")
    else:
        pause_btn.configure(text="⏸ Pause")
        for r in range(size):
            for c in range(size):
                if (r, c) not in given_cells:
                    entries[r][c].configure(state="normal")

# ─────────────────────────────────────────────
#  Check Solution
# ─────────────────────────────────────────────
def is_valid_move(board, row, col, num):
    size = len(board)
    block = int(np.sqrt(size))
    for i in range(size):
        if board[row][i] == num or board[i][col] == num:
            return False
    sr, sc = block*(row//block), block*(col//block)
    for r in range(sr, sr+block):
        for c in range(sc, sc+block):
            if board[r][c] == num:
                return False
    return True

def check_solution():
    board = get_board()
    size = len(board)
    for r in range(size):
        for c in range(size):
            num = board[r][c]
            if num == 0:
                messagebox.showwarning("Incomplete", "Board is not complete yet.")
                return False
            board[r][c] = 0
            if not is_valid_move(board, r, c, num):
                entries[r][c].configure(border_color="#FF0000")
                app.after(1200, lambda rr=r, cc=c: entries[rr][cc].configure(border_color="#12EA19"))
                messagebox.showerror("Error", f"Incorrect value at row {r+1}, column {c+1}.")
                board[r][c] = num
                return False
            board[r][c] = num
    stop_timer()
    m, s = divmod(timer_seconds, 60)
    messagebox.showinfo("Congratulations! 🎉", f"Correct solution!\nTime: {m:02d}:{s:02d}")
    return True

# ─────────────────────────────────────────────
#  Solve (Auto)
# ─────────────────────────────────────────────
def solve_board():
    board = get_board()
    solved = copy.deepcopy(board)
    if backtrack_solve(solved):
        for r in range(len(solved)):
            for c in range(len(solved)):
                set_cell(r, c, solved[r][c])
        solution_board.clear()
        solution_board.extend(copy.deepcopy(solved))
        stop_timer()
        messagebox.showinfo("Solved", "Puzzle solved automatically!")
    else:
        messagebox.showerror("Error", "No solution found for the current board.")

# ─────────────────────────────────────────────
#  Save & Resume
# ─────────────────────────────────────────────
def save_game():
    size = current_grid_size
    board = get_board()
    data = {
        "size": size,
        "board": board,
        "solution": solution_board if solution_board else [],
        "given_cells": list(given_cells),
        "mistakes": mistakes,
        "timer": timer_seconds,
        "difficulty": difficulty_var.get()
    }
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f)
    messagebox.showinfo("Saved", "Game saved successfully!")

def resume_game():
    global mistakes, game_over_flag
    if not os.path.exists(SAVE_FILE):
        messagebox.showinfo("Resume", "No saved game found.")
        return
    with open(SAVE_FILE, "r") as f:
        data = json.load(f)

    size = data["size"]
    board = data["board"]
    sol = data["solution"]
    gc = [tuple(x) for x in data["given_cells"]]
    saved_mistakes = data["mistakes"]
    saved_timer = data["timer"]

    size_map = {4: "4x4", 9: "9x9", 16: "16x16"}
    size_choice.set(size_map.get(size, "9x9"))
    create_grid(size)

    given_cells.clear()
    given_cells.update(gc)
    solution_board.clear()
    solution_board.extend(sol)

    unlock_all_cells()
    for r in range(size):
        for c in range(size):
            set_cell(r, c, board[r][c])
    lock_given_cells()
    rebind_cells()

    mistakes = saved_mistakes
    mistakes_label.configure(text=f"❌ Mistakes: {mistakes}/{MAX_MISTAKES}")

    global timer_seconds
    timer_seconds = saved_timer
    m, s = divmod(timer_seconds, 60)
    timer_label.configure(text=f"⏱ {m:02d}:{s:02d}")

    reset_state()
    game_over_flag = False
    start_timer()
    messagebox.showinfo("Resumed", "Game resumed!")

# ─────────────────────────────────────────────
#  Grid Size Selector (top-right of info)
# ─────────────────────────────────────────────
def set_grid_size(choice):
    size = grid_sizes[choice]
    create_grid(size)
    given_cells.clear()
    solution_board.clear()
    reset_state()
    reset_timer()
    stop_timer()

# ─────────────────────────────────────────────
#  UI – Difficulty + Grid Size Row
# ─────────────────────────────────────────────
controls_row = ctk.CTkFrame(frame, fg_color="transparent")
controls_row.pack(fill="x", padx=6, pady=(2, 4))

ctk.CTkLabel(controls_row, text="Difficulty:", font=("Arial", 13, "bold"), text_color="black").pack(side="left", padx=(6, 2))
difficulty_var = ctk.StringVar(value="Medium")
diff_menu = ctk.CTkOptionMenu(
    controls_row, variable=difficulty_var,
    values=["Easy", "Medium", "Hard", "Expert"],
    width=120, font=("Arial", 13)
)
diff_menu.pack(side="left", padx=4)

ctk.CTkLabel(controls_row, text="Size:", font=("Arial", 13, "bold"), text_color="black").pack(side="left", padx=(12, 2))
size_choice = ctk.StringVar(value="9x9")
size_menu = ctk.CTkOptionMenu(
    controls_row, variable=size_choice,
    values=["4x4", "9x9", "16x16"],
    command=set_grid_size, width=100, font=("Arial", 13)
)
size_menu.pack(side="left", padx=4)

pause_btn = ctk.CTkButton(
    controls_row, text="⏸ Pause",
    command=toggle_pause,
    fg_color="#555555", hover_color="#333333",
    font=("Arial", 13, "bold"), width=100
)
pause_btn.pack(side="right", padx=6)

# ─────────────────────────────────────────────
#  Grid (9×9 default)
# ─────────────────────────────────────────────
create_grid(9)

# ─────────────────────────────────────────────
#  UI – Button Rows
# ─────────────────────────────────────────────
def make_btn(parent, text, cmd, color, hover, row, col, colspan=1):
    b = ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=color, hover_color=hover,
        font=("Arial", 13, "bold"), width=120
    )
    b.grid(row=row, column=col, columnspan=colspan, padx=5, pady=4)
    return b

# Row 1
btn_frame1 = ctk.CTkFrame(frame, fg_color="transparent")
btn_frame1.pack(pady=4)

make_btn(btn_frame1, "🎲 New Game",   lambda: new_game(),     "#27AE60", "#1E8449", 0, 0)
make_btn(btn_frame1, "📅 Daily",      daily_challenge,        "#2980B9", "#21618C", 0, 1)
make_btn(btn_frame1, "💡 Hint",       hint,                   "#D4AC0D", "#B7950B", 0, 2)
make_btn(btn_frame1, "📂 Load",       load_puzzle,            "#4CAF50", "#45a049", 0, 3)

# Row 2
btn_frame2 = ctk.CTkFrame(frame, fg_color="transparent")
btn_frame2.pack(pady=4)

make_btn(btn_frame2, "↩ Undo",        undo,                   "#1A5276", "#154360", 0, 0)
make_btn(btn_frame2, "↪ Redo",        redo,                   "#1A5276", "#154360", 0, 1)
make_btn(btn_frame2, "✔ Check",       check_solution,         "#3498DB", "#2980B9", 0, 2)
make_btn(btn_frame2, "⚡ Solve",      solve_board,            "#9B59B6", "#8E44AD", 0, 3)

# Row 3
btn_frame3 = ctk.CTkFrame(frame, fg_color="transparent")
btn_frame3.pack(pady=4)

make_btn(btn_frame3, "🗑 Clear",       clear_board,            "#E67E22", "#CA6F1E", 0, 0)
make_btn(btn_frame3, "💾 Save",        save_game,              "#1ABC9C", "#17A589", 0, 1)
make_btn(btn_frame3, "📁 Resume",      resume_game,            "#1ABC9C", "#17A589", 0, 2)

# ─────────────────────────────────────────────
#  Keyboard shortcuts
# ─────────────────────────────────────────────
app.bind("<Control-z>", lambda e: undo())
app.bind("<Control-y>", lambda e: redo())
app.bind("<Control-s>", lambda e: save_game())
app.bind("<Control-h>", lambda e: hint())

# ─────────────────────────────────────────────
#  Start timer loop & run
# ─────────────────────────────────────────────
update_timer()

app.mainloop()
