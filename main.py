import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

OCCUPIED = -2
FREE_FOR_WHOLE_WEEK = 10080


def get_reservations(session: requests.Session) -> list[str]:
    index = 1
    data = {"pStart": index,
            "pSuchbegriff": "",
            "pGebaeudebereich": 33,
            "pGebaeude": 0,
            "pVerwendung": 41,
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


def main():
    session = requests.session()
    reservations = get_reservations(session)

    all_rooms_info: list[tuple[str, int]] = []
    for reservation in reservations:
        room_info = minutes_until_next_lecture(reservation)
        all_rooms_info.append(room_info)

    all_rooms_info_sorted = sorted(
        all_rooms_info, key=lambda x: x[1], reverse=True)

    for room_info in all_rooms_info_sorted:
        room_name, time_left = room_info
        room_name_width = 55
        state_col_width = 10
        if time_left == OCCUPIED:
            print(
                f"{room_name:<{room_name_width}}{'State:':<{state_col_width}}Occupied")
        elif time_left == FREE_FOR_WHOLE_WEEK:
            print(
                f"{room_name:<{room_name_width}}{'State:':<{state_col_width}}Free for the entire week")
        else:
            hours_left = time_left // 60
            minutes_left = time_left % 60
            time_str = f"Free for {hours_left} hours {minutes_left} minutes"
            print(
                f"{room_name:<{room_name_width}}{'State:':<{state_col_width}}{time_str}")


if __name__ == "__main__":
    main()
