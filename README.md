# How to use

- Install all requirements from requirements.txt
- See the help text after running:
    ```python
    python main.py -h
    ```

# What it does

- Fetches information from https://campus.tum.de/tumonline/wbSuche.raumSuche and iterates through all of the returned rooms in a multi threaded(!) manner
- Displays how many hours and minutes are left until a room is occupied by some event in a pretty way
