# Coop crawl

Annahme: prof-seiten haben keine bot-detection
aber javascript / client-side-rendering sollten wir schon unterstützen
also nicht nur `requests`, sondern selenium
mit adblock

nur feste Links, nicht anderen Links folgen

Konfiguration via config.py

testen mit pytest
uv fürs bauen
ruff formatting and linting
keine DB, einfach in memory
    - beim ersten Mal reinladen wird nie gesendet; diff gegen nichts ist immer ignoriert



- coding rules für agenten
    - Ruff-compatible formatting
    - 100% typed, kein type sollte CI failure sein
        - typical eval through ty and mypy (both)
    - No mistakes pls
    - kein globaler mutable state
    - 
    

- Programmiersprache: Python


subselection über xpath 'bitte schau dir nur subtree vom html an'
xpath-subselect händisch zur url-Liste dazupflegen
    - Dieser wird per Firefox dev tools; element picker; rechtsklick; kopieren; xpath generiert
    - Optional; defaulted zu `/` (nicht empfehlenswert)
Evaluation durch LLM ob Änderung spannend

maximale loading time bis timeout; dann nimmt man was es gibt

Änderungen batchen - nur eine Nachricht bei mehrfacher änderung

Wie notifyen: TG-bot schreibt in gemutete Gruppe, aber @-ted dich wenn score der Änderung sehr hoch


- on 3xx HTTP: follow redirect
- On 4xx HTTP: bei error: telegram-nachricht und dann weiter anfragen bis sich etwas ändert
    - 419 request limit -> backoff \\ eher nicht so wichtig
- On 5xx HTTP: log print




- Ablauf:

alle 10 Minuten (sollte default attribute in Dataclass für neuen Entry sein, alles sollte konfigurierbar sein)

- Jeder Entry hat eine Dataclass
    - Diese hat eine Menge an extraattributen (wie zB poll time) mit sensible default values
    - Jeder Entry wird ne async function, die ihren eigenen state speichert, und im sleep yielded

state pro Entry (webseite):
    config (timeouts, poll time, xpath) des Entry (immutable)
    letzte Version

```python

class NotificationLevel(enum.Enum):
    NO_PING = 0
    NORMAL_PING = 1
    MENTION_PING = 2
    
# effectively immutable state, as we only use stateless openAI API calls
client = openai.Client(...)
    
@dataclass
class LLMState:
    system_prompt: str
    
    @classmethod
    def evaluate(diff: str) -> NotificationLevel:
        """sends the diff to the LLM, and gives back whether the user should be notified"""
        ...

@dataclass
class Entry:
    ...
    url: str
    xpath: str
    llm_state: LLMState
    
    timeout_secs: int = 20 # until it stops loading
    poll_interval_secs: int = 5*60 # awaiting sleep time between reqs
    
```

```python
# config.py

ALL_ENTRIES: list[Entry] = [
    Entry(...)
    Entry(...),
    Entry(...)
]
```

mainloop:
    webseite in selenium aufrufen
    js laden lassen mit timeout
    mit xpath Inhalt holen
    diff wird in lokale funktion gespeichert; bleibt ja im scope weil die nie ended und immer nur yielded
    -> ja, dann an llm schicken
    llm sagt relevant?
    -> ja, dann an alert-modul weitergeben




























