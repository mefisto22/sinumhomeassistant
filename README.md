# Tech Sinum integráció Home Assistanthoz

Jelenleg az integráció **alfa fázisban** van, ezért **csak saját felelősségre** használd!

## Telepítés

Az integráció telepítése után a vezérlő **címét** (IP vagy hostnév, pl. `192.168.1.50` vagy `sinum.local`, opcionálisan porttal) és az **API tokent** kell megadnod. A beállításkor az integráció ellenőrzi a kapcsolatot és a tokent.

- Több SINUM vezérlő is felvehető, mindegyik külön eszközként jelenik meg.
- Ha a token lejár vagy megváltozik, a Home Assistant újrahitelesítést kér.
- A vezérlő címe és tokenje később az integráció **Újrakonfigurálás** menüjében módosítható.
- Az eszközök állapotát az integráció 2 másodpercenként, egyetlen közös lekérdezéssel frissíti. Ha a vezérlő nem érhető el, vagy egy eszköz offline, az entitások „nem elérhető” állapotba kerülnek.

Verziózás: `ÉV.HÓNAP.SORSZÁM` (pl. `2026.10.01`).

## Integrált eszközök

| Eszközök                  | Támogatás                     |
|---------------------------|-------------------------------|
| Relék                     | WTP és SBUS                  |
| Termosztátok              | Virtuális eszközként          |
| RGB kontrollerek          | WTP és SBUS                  |
| Redőny vezérlők           | WTP és SBUS                  |
| Fényérzékelők             | WTP és SBUS                  |
| Hőmérsékletek             | WTP és SBUS                  |
| Páratartalom              | WTP és SBUS                  |
| Hőmérséklet szabályzók    | Nincsenek, mivel virtuális eszközként vannak felvéve |
| Bináris bemenetek         | WTP és SBUS                  |
| Akkumulátor szenzorok     | WTP és SBUS                  |


---


# Tech Sinum Integration for Home Assistant

The integration is currently in the **alpha phase**, so **use it at your own risk**!

## Installation

After installing the integration, enter the controller **host** (IP or hostname, e.g. `192.168.1.50` or `sinum.local`, optionally with a port) and the **API token**. The connection and the token are verified during setup.

- Multiple SINUM controllers can be added; each one appears as its own device.
- If the token expires or changes, Home Assistant asks you to re-authenticate.
- The host and token can be changed later with the integration's **Reconfigure** option.
- Device states are refreshed every 2 seconds with a single shared poll. If the controller is unreachable or a device is offline, its entities become unavailable.

Versioning: `YEAR.MONTH.NN` (e.g. `2026.10.01`).

## Supported Devices

| Devices                  | Support                       |
|--------------------------|-------------------------------|
| Relays                   | WTP and SBUS                 |
| Thermostats              | As virtual devices           |
| RGB controllers          | WTP and SBUS                 |
| Shutter controllers      | WTP and SBUS                 |
| Light sensors            | WTP and SBUS                 |
| Temperatures             | WTP and SBUS                 |
| Humidity                 | WTP and SBUS                 |
| Temperature regulators   | None, as they are treated as virtual devices |
| Binary inputs            | WTP and SBUS                 |
| Battery sensors          | WTP and SBUS                 |


---