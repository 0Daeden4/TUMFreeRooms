import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import itertools
from argparse import ArgumentParser, Namespace
import re


OCCUPIED = -2
FREE_FOR_WHOLE_WEEK = 10080

ALLE_VERWENDUNGSTYPEN = {"Alle-Verwendungstypen": 0}
AUFZUG = {"Aufzug": 4}
BESPRECHUNGSRAUM = {"Besprechungsraum": 196}
BIBLIOTHEK = {"Bibliothek": 10}
FREIFLACHE = {"Freiflache": 217}
HORSAAL = {"Horsaal": 20}
PRAKTIKUMSRAUM_CHEMIE = {"Praktikumsraum-chemie": 212}
PRAKTIKUMSRAUM_EDV = {"Praktikumsraum-edv": 213}
PRAKTIKUMSRAUM_PHYSIK = {"Praktikumsraum-physik": 211}
SEKRETARIAT = {"Sekretariat": 40}
SEMINARRAUM = {"Seminarraum": 41}
SPORTRAUM = {"Sportraum": 128}
SPRACHLABOR = {"Sprachlabor": 135}
STUDENTENARBEITSRAUM = {"Studentenarbeitsraum": 208}
TURNSAAL = {"Turnsaal": 191}
UBUNGSRAUM = {"Ubungsraum": 131}
UNTERRICHTSRAUM = {"Unterrichtsraum": 130}
ZEICHENSAAL = {"Zeichensaal": 55}

ALL_USAGES: dict[str, int] = {**ALLE_VERWENDUNGSTYPEN, **AUFZUG, **BESPRECHUNGSRAUM, **BIBLIOTHEK, **FREIFLACHE, **HORSAAL, **PRAKTIKUMSRAUM_CHEMIE, **PRAKTIKUMSRAUM_EDV,
                              **PRAKTIKUMSRAUM_PHYSIK, **SEKRETARIAT, **SEMINARRAUM, **SPORTRAUM, **SPRACHLABOR, **STUDENTENARBEITSRAUM, **TURNSAAL, **UBUNGSRAUM, **UNTERRICHTSRAUM, **ZEICHENSAAL}

CHEMIE = 36
ELEKTROTECHNIK = 302
GARCHING_SONST = 57
MI = 33
MW = 34
PHYSIK = 35
STAMM_NORD = 27
STAMM_SUD = 26
STAMM_SUDOST = 25
STAMM_SUDWEST = 24
STAMM_ZENTRAL = 23


def get_reservations(session: requests.Session, search_text: str = "", building_category: int = 33, usage: int = 41) -> list[str]:
    index = 1
    data = {"pStart": index,
            "pSuchbegriff": search_text,
            "pGebaeudebereich": building_category,
            "pGebaeude": 0,
            "pVerwendung": usage,
            "pVerwalter": 1}

    response = session.post(
        "https://campus.tum.de/tumonline/wbSuche.raumSuche", data=data)

    soup = BeautifulSoup(response.text, "html.parser")

    all_reservations = []
    while (reservations := soup.find_all('td', class_='C')):
        all_reservations.extend(reservations)
        index += 30
        data["pStart"] = index
        response = session.post(
            "https://campus.tum.de/tumonline/wbSuche.raumSuche", data=data)
        soup = BeautifulSoup(response.text, "html.parser")

    reservation_links: list[str] = []
    for reservation in all_reservations:
        a = reservation.find("a")
        if a and a.get("href"):
            full_url = urljoin("https://campus.tum.de/tumonline/", a['href'])
            reservation_links.append(full_url)

    return reservation_links


def minutes_until_next_lecture(url) -> tuple[str, int]:

    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    lecture = soup.find(
        "span", class_="s")
    lecture_name = lecture.get_text()

    now = datetime.now()

    upcoming_events = []
    for container in soup.find_all('div', class_='cocal-ev-container'):
        data = container.get('data-event')
        if data and '"start":"' in data and '"end":"' in data:
            start_str = data.split('"start":"')[1].split('"')[0]
            end_str = data.split('"end":"')[1].split('"')[0]
            start_time = datetime.strptime(start_str, "%d%m%Y%H%M")
            end_time = datetime.strptime(end_str, "%d%m%Y%H%M")

            if start_time <= now <= end_time:
                return (lecture_name, OCCUPIED)

            if start_time > now:
                upcoming_events.append(start_time)

    if upcoming_events:
        next_lecture = min(upcoming_events)
        delta = next_lecture - now
        minutes_left = int(delta.total_seconds() // 60)
        return (lecture_name, minutes_left)
    else:
        return (lecture_name, FREE_FOR_WHOLE_WEEK)


def work_thread(reservations: list[str]) -> list[tuple[str, int]]:
    rooms_info: list[tuple[str, int]] = []
    for reservation in reservations:
        room_info = minutes_until_next_lecture(reservation)
        rooms_info.append(room_info)

    return rooms_info


def fetch_multi_thread(reservations: list[str], max_workers: int = 4) -> list[tuple[str, int]]:
    reservations_length = len(reservations)
    if reservations_length == 0:
        return [("No reservations found", 0)]
    slice_size = reservations_length // max_workers
    extra = reservations_length % max_workers
    partitions: list[list[str]] = []
    start = 0
    if max_workers >= reservations_length:
        partitions = [[elem] for elem in reservations]
        max_workers = reservations_length
    else:
        for i in range(0, max_workers):
            end = start+slice_size
            if i < extra:
                end += 1
            slice = reservations[start:end]
            if i == max_workers:
                slice.append(reservations[-1])
            partitions.append(slice)
            start = end

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        workers = executor.map(
            lambda load: work_thread(load), partitions
        )

    all_rooms_info = list(itertools.chain.from_iterable(
        result for result in workers))

    return all_rooms_info


def to_string(all_rooms_info: list[tuple[str, int]]) -> str:
    string = ""
    room_name_width = 58
    state_col_width = 40
    for room_info in all_rooms_info:
        room_name, time_left = room_info
        room_ids = re.findall(r'\(([^)]*)\)', room_name)
        if len(room_ids) != 0:
            room_nav_link = urljoin("https://nav.tum.de/room/", room_ids[-1])
        else:
            room_nav_link = ""
        string += f"{room_name:<{room_name_width}}"
        if time_left == OCCUPIED:
            string += f"{'State: Occupied':<{state_col_width}}"
        elif time_left == FREE_FOR_WHOLE_WEEK:
            string += f"{'State: Free for the entire week':<{state_col_width}}"
        else:
            hours_left = time_left // 60
            minutes_left = time_left % 60
            time_str = f"Free for {hours_left} hours {minutes_left} minutes"
            string += f"{f'State: {time_str}':<{state_col_width}}"
        string += f"Link: {room_nav_link}\n"

    return string


def calculate(session: requests.Session, threads: int = 4, search_text: str | None = "", building_category: int = 33, usage: int | None = 41) -> str:
    if search_text is None:
        search_text = ""
    if usage is None:
        usage = 41
    reservations = get_reservations(
        session, search_text, building_category, usage)

    all_rooms_info = fetch_multi_thread(reservations, threads)

    all_rooms_info_sorted = sorted(
        all_rooms_info, key=lambda x: x[1], reverse=True)

    return to_string(all_rooms_info_sorted)


def main(args: Namespace):
    session = requests.session()
    thread_count = args.threads

    if args.search:
        search_text = args.search
        forbidden = "|-()²³\"&*#=§%/{}[]'´+?~_:.,;!^°<>$"
        escaped = re.escape(forbidden)
        pattern = rf"[^{escaped}]"
        pattern_2 = r"[^*%]{2,}"

        if len(re.findall(pattern, search_text)) < 3:
            raise ValueError(
                r"""You must include at least three characters other than '|-()²³"&*#=§%/{}[]''´+?~_:.,;!^°<>$' in your search text!""")
        elif not re.search(pattern_2, search_text):
            raise ValueError(
                "You must use at least two consecutive characters that are not '*' or '%'.")
    else:
        search_text = ""

    for name in args.usage:
        usage = ALL_USAGES.get(name)
        print("\033[1m\033[34m", end="")
        print("┌"+name)
        print("\033[0m", end="")
        for building in args.building:
            print("\033[1m", end="")
            print("\033[34m│   \033[35m┌"+building)
            print("\033[0m", end="")
            if building == "Chemie":
                output = calculate(
                    session, thread_count, building_category=CHEMIE, usage=usage, search_text=search_text)
            elif building == "Elektrotechnik":
                output = calculate(
                    session, thread_count, building_category=ELEKTROTECHNIK, usage=usage, search_text=search_text)
            elif building == "Garching-Sonst":
                output = calculate(
                    session, thread_count, building_category=GARCHING_SONST, usage=usage, search_text=search_text)
            elif building == "MI":
                output = calculate(
                    session, thread_count, building_category=MI, usage=usage, search_text=search_text)
            elif building == "MW":
                output = calculate(
                    session, thread_count, building_category=MW, usage=usage, search_text=search_text)
            elif building == "Physik":
                output = calculate(
                    session, thread_count, building_category=PHYSIK, usage=usage, search_text=search_text)
            elif building == "Stamm-Sud":
                output = calculate(
                    session, thread_count, building_category=STAMM_SUD, usage=usage, search_text=search_text)
            elif building == "Stamm-Nord":
                output = calculate(
                    session, thread_count, building_category=STAMM_NORD, usage=usage, search_text=search_text)
            elif building == "Stamm-Sudost":
                output = calculate(
                    session, thread_count, building_category=STAMM_SUDOST, usage=usage, search_text=search_text)
            elif building == "Stamm-Sudwest":
                output = calculate(
                    session, thread_count, building_category=STAMM_SUDWEST, usage=usage, search_text=search_text)
            elif building == "Stamm-Zentral":
                output = calculate(
                    session, thread_count, building_category=STAMM_ZENTRAL, usage=usage, search_text=search_text)
            else:
                print("Please specify a building.")
                continue
            for line in output.splitlines():
                print("\033[34m│   \033[35m│\033[0m"+line)
            print("\033[1m\033[34m│   \033[1m\033[35m└\033[0m")

        print("\033[1m\033[34m└\033[0m")


if __name__ == "__main__":
    argp = ArgumentParser()
    argp.add_argument("--building", "-b", type=str, choices=["Chemie", "Elektrotechnik", "Garching-Sonst",
                      "MI", "MW", "Physik", "Stamm-Sud", "Stamm-Nord", "Stamm-Sudost", "Stamm-Sudwest", "Stamm-Zentral"], required=True, action="append")
    argp.add_argument("--usage", "-u", type=str, choices=["Alle-Verwendungstypen", "Aufzug", "Bibliothek",
                      "Freiflache", "Horsaal", "Praktikumsraum-chemie", "Praktikumsraum-edv", "Praktikumsraum-physik", "Sekretariat", "Seminarraum", "Sportraum", "Sprachlabor", "Studentenarbeitsraum", "Turnsaal", "Ubungsraum", "Unterrichtsraum", "Zeichensaal"], required=True, action="append")
    argp.add_argument("-threads", "-t", type=int, required=False, default=4)
    argp.add_argument("-search", "-s", type=str, required=False,
                      help=(r"""You must include at least three characters other than '|-()²³"&*#=§%%/{}[]''´+?~_:.,;!^°<>$' in your search text!""" +
                            "Accepts wildcards such as (*, _ and %%)." +
                            " With 'something' you get 'Something'." +
                            " With '*something*' you get 'Something', 'StuffSomething' and 'SomethingStuff'." +
                            " With 'Something%%' you get 'SomethingStuff'." +
                            " With 'S_mething' you get 'Something' and 'Samething'." +
                            "Example: '*01.0*) *01.1*)' searches the rooms on the first floor etc."
                            )
                      )
    args = argp.parse_args()
    main(args)
