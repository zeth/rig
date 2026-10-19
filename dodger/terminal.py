"""Terminal UI for the human player of a local Dodger game."""

import curses
import urllib.error

from client import get_game, send_action


def render(state):
    width = state["arena_width"]
    height = state["arena_height"]
    cells = [[" " for _ in range(width)] for _ in range(height)]
    for obstacle in state["obstacles"]:
        if 0 <= obstacle["y"] < height:
            for x in range(obstacle["x"], obstacle["x"] + obstacle["width"]):
                if 0 <= x < width:
                    cells[obstacle["y"]][x] = "#"
    floor = height - 1
    human_x = state["human"]["x"]
    bot_x = state["bot"]["x"]
    if 0 <= human_x < width:
        cells[floor][human_x] = "H"
    if 0 <= bot_x < width:
        cells[floor][bot_x] = "X" if human_x == bot_x else "B"
    lines = ["+" + "-" * width + "+"]
    lines.extend("|" + "".join(row) + "|" for row in cells)
    lines.append("+" + "-" * width + "+")
    lines.append(
        f"Human lives: {state['human']['lives']}  "
        f"Bot lives: {state['bot']['lives']}  Tick: {state['tick']}"
    )
    if state["status"] == "Finished":
        lines.append(f"Winner: {state['winner']}  Press q to quit")
    elif state["status"] == "Waiting":
        lines.append("Waiting for both players to join")
    else:
        lines.append("A/D or arrows: move   Space: shove   Q: quit")
    return lines


def play(screen, base_url):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.timeout(100)
    state = get_game(base_url)
    while True:
        lines = render(state)
        screen.erase()
        max_y, max_x = screen.getmaxyx()
        if max_y <= len(lines) or max_x <= max(map(len, lines)):
            screen.addstr(0, 0, "Terminal too small for Dodger"[:max(0, max_x - 1)])
        else:
            for y, line in enumerate(lines):
                screen.addstr(y, 0, line)
        screen.refresh()

        key = screen.getch()
        if key in (ord("q"), ord("Q")):
            return
        if state["status"] == "Finished":
            continue
        move = "Stay"
        if key in (ord("a"), ord("A"), curses.KEY_LEFT):
            move = "Left"
        elif key in (ord("d"), ord("D"), curses.KEY_RIGHT):
            move = "Right"
        try:
            state = send_action(base_url, 1, {"move": move, "shove": key == ord(" ")})
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
            state = get_game(base_url)


def run(base_url):
    curses.wrapper(play, base_url)
