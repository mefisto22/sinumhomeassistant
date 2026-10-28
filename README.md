# Tech Sinum integráció Home Assistanthoz

[![Validate](https://github.com/mefisto22/sinumhomeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/mefisto22/sinumhomeassistant/actions/workflows/validate.yml)

Jelenleg az integráció **alfa fázisban** van, ezért **csak saját felelősségre** használd!

A SINUM központi egységet a helyi API-n keresztül, felhő nélkül kapcsolja a Home Assistanthoz. Legalább Home Assistant 2025.1 kell hozzá.

## Telepítés

1. HACS → jobb felső menü → **Egyéni tárolók**: `https://github.com/mefisto22/sinumhomeassistant`, típus: **Integráció**.
2. Telepítsd a *SINUM Integration*-t, majd indítsd újra a Home Assistantot.
3. **Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása → SINUM**.
4. Add meg a vezérlő **címét** (IP vagy hostnév, pl. `192.168.1.50` vagy `sinum.local`, opcionálisan porttal) és az **API tokent**. A tokent a SINUM webes felületén lehet létrehozni. A beállításkor az integráció ellenőrzi a kapcsolatot és a tokent.

## Működés

- **Több vezérlő** is felvehető; ugyanaz a vezérlő kétszer nem.
- **Frissítés:** az eszközök állapotát az integráció 2 másodpercenként, egyetlen közös lekérdezéssel frissíti. Ha a vezérlő nem érhető el, vagy egy eszközt a vezérlő offline-nak jelez, az entitások „nem elérhető” állapotba kerülnek.
- **Újrahitelesítés:** ha a token lejár vagy megváltozik, a Home Assistant új tokent kér.
- **Újrakonfigurálás:** a vezérlő címe és tokenje az integráció menüjében módosítható.
- **Eszközök:** minden fizikai SINUM modul (pl. egy R-S3 szobai panel vagy egy PS-08m relémodul) egy Home Assistant eszköz a *SINUM All-in-One* vezérlő alatt, a modell- és szoftververzióval. Az entitások a SINUM-beli nevüket kapják, az eszköznév előtagja nélkül (pl. *Földszint szoba* → *Hőmérséklet*).
- **Termosztát:** a virtuális termosztát a hozzárendelt szobai panel eszközére kerül, és az eszköz a termosztát szobájáról kapja a nevét. A panel és a termosztát saját mérése külön névvel jelenik meg (*Hőmérséklet*, ill. *Termosztát hőmérséklet*). A modul nélküli eszközök (pl. hozzárendelés nélküli termosztát) külön eszközök maradnak.
- **Területek:** az eszközök a SINUM szobájuk alapján területet kapnak az első létrehozáskor. A kézzel átállított területet a frissítés nem írja felül.
- **Új és megszűnt eszközök:** a vezérlőn újonnan megjelenő eszközök újratöltés nélkül megjelennek. A vezérlőről eltávolított eszköz a HA-ban kézzel törölhető (*Eszköz → Törlés*).
- **Mértékegységek:** `us` régióra állított vezérlőn a hőmérséklet °F-ben jön, a fényerősség pedig luxra van átváltva.
- **Hibaüzenetek:** ha egy parancs nem sikerül, magyar vagy angol nyelvű, érthető hibaüzenet jelenik meg.
- **Diagnosztika:** *Eszközök és szolgáltatások → SINUM → ⋮ → Diagnosztika letöltése*. Az IP-cím, a token és a szobai panelek PIN-kódja ki van takarva.

## Támogatott eszközök

| Eszköz | Osztály | Home Assistant entitás |
|---|---|---|
| Relé | SBUS, WTP | kapcsoló |
| RGB vezérlő | SBUS, WTP | lámpa: be/ki, fényerő, szín, ahol a vezérlő tudja, színhőmérséklet |
| Redőnyvezérlő | SBUS, WTP | redőny: nyit, zár, STOP; pozíció és billentés, ha a vezérlő támogatja |
| Hőmérséklet-, páratartalom-, fényérzékelő | SBUS, WTP | szenzor |
| Mozgásérzékelő, kétállapotú bemenet | SBUS, WTP | bináris szenzor |
| Akkumulátor | SBUS, WTP | szenzor (fizikai eszközönként egy) |
| Analóg kimenet, PWM | SBUS, WTP | szám |
| Termosztát | virtuális | klíma: üzemmód (fűtés, hűtés, ki), célhőmérséklet, ütemezett és állandó mód presetként; mellette hőmérséklet- és páratartalom-szenzor |

A termosztát üzemmódját és célhőmérsékletét külön szenzorként, választóként és számként is el lehet érni. Ezek a klíma entitást duplikálják, ezért új telepítésnél alapból le vannak tiltva.

## Frissítés régebbi verzióról

- Az **entity_id-k nem változnak**, így az automatizmusok, szkriptek és dashboardok továbbra is működnek.
- A 2026.10.03 óta minden SINUM eszköz külön HA eszköz. Ami eddig a *SINUM All-in-One* eszközt célozta `device_id`-vel (pl. `climate.set_temperature` `target: device_id`), azt át kell írni entity_id-re vagy területre.
- A modulonkénti csoportosításra frissítéskor a korábbi, végpontonkénti eszközök entitásai (a letiltottak is) átkerülnek a modul eszközére, a régi eszközök pedig törlődnek. Az új eszköz a régiek területét kapja (elsősorban a termosztátét). A régi eszközökre `device_id`-vel hivatkozó automatizmusokat át kell írni; a kézzel adott eszköznevek nem öröklődnek.

## Fejlesztés

A tesztek valódi Home Assistant tesztpéldányon, hamis SINUM API-val futnak:

```bash
pip install -r requirements_test.txt
pytest
mypy
```

A kód szigorú típusellenőrzésen (`mypy --strict`) megy át. A GitHub Actions minden pushnál lefuttatja a hassfest és a HACS ellenőrzést, a típusellenőrzést, valamint a teszteket a Home Assistant 2025.1, 2026.2 és 2026.10 verzióján.

Verziózás: `ÉV.HÓNAP.SORSZÁM` (pl. `2026.10.01`).


---


# Tech Sinum Integration for Home Assistant

The integration is currently in the **alpha phase**, so **use it at your own risk**!

It connects a SINUM central unit to Home Assistant over the local API, with no cloud. Requires Home Assistant 2025.1 or newer.

## Installation

1. HACS → top-right menu → **Custom repositories**: `https://github.com/mefisto22/sinumhomeassistant`, type **Integration**.
2. Install *SINUM Integration* and restart Home Assistant.
3. **Settings → Devices & services → Add integration → SINUM**.
4. Enter the controller **host** (IP or hostname, e.g. `192.168.1.50` or `sinum.local`, optionally with a port) and the **API token**. You can create the token in the SINUM web app. The connection and the token are verified during setup.

## How it works

- **Multiple controllers** can be added; the same controller cannot be added twice.
- **Updates:** device states are refreshed every 2 seconds with a single shared poll. If the controller is unreachable, or it reports a device as offline, the entities become unavailable.
- **Re-authentication:** if the token expires or changes, Home Assistant asks for a new one.
- **Reconfigure:** the host and token can be changed from the integration's menu.
- **Devices:** every physical SINUM module (e.g. an R-S3 room panel or a PS-08m relay module) is one Home Assistant device under the *SINUM All-in-One* controller, with its model and software version. Entities get their SINUM name without the device name prefix (e.g. *Ground floor room* → *Temperature*).
- **Thermostat:** a virtual thermostat is placed on the device of its assigned room panel, and that device is named after the thermostat's room. The panel's and the thermostat's own readings get distinct names (*Temperature* and *Thermostat temperature*). Devices without a module (e.g. a thermostat with no assignments) stay separate devices.
- **Areas:** devices get an area from their SINUM room when they are first created. An area you set by hand is never overwritten.
- **New and removed devices:** devices added on the controller appear without a reload. A device removed from the controller can be deleted in HA (*Device → Delete*).
- **Units:** on a controller set to the `us` region, temperatures are in °F and illuminance is converted to lux.
- **Error messages:** when a command fails you get a clear message in English or Hungarian.
- **Diagnostics:** *Devices & services → SINUM → ⋮ → Download diagnostics*. The IP address, the token and the room panels' PIN code are redacted.

## Supported devices

| Device | Class | Home Assistant entity |
|---|---|---|
| Relay | SBUS, WTP | switch |
| RGB controller | SBUS, WTP | light: on/off, brightness, color, and color temperature where the controller supports it |
| Blind controller | SBUS, WTP | cover: open, close, STOP; position and tilt when the controller supports them |
| Temperature, humidity, light sensor | SBUS, WTP | sensor |
| Motion sensor, two-state input | SBUS, WTP | binary sensor |
| Battery | SBUS, WTP | sensor (one per physical device) |
| Analog output, PWM | SBUS, WTP | number |
| Thermostat | virtual | climate: mode (heat, cool, off), target temperature, schedule and constant mode as presets; plus temperature and humidity sensors |

The thermostat mode and target temperature are also available as a separate sensor, select and number. They duplicate the climate entity, so on new installs they are disabled by default.

## Upgrading from an older version

- **Entity IDs do not change**, so automations, scripts and dashboards keep working.
- Since 2026.10.03 every SINUM device is its own HA device. Anything that targeted the *SINUM All-in-One* device by `device_id` (e.g. `climate.set_temperature` with `target: device_id`) must be changed to target entity IDs or an area.
- When upgrading to per-module devices, the entities of the old per-endpoint devices (disabled ones included) move to the module's device and the old devices are deleted. The new device takes the old devices' area (the thermostat's first). Automations that reference the old devices by `device_id` must be updated; device names set by hand are not carried over.

## Development

The tests run against a real Home Assistant test instance with a fake SINUM API:

```bash
pip install -r requirements_test.txt
pytest
mypy
```

The code passes strict type checking (`mypy --strict`). GitHub Actions runs hassfest, the HACS validation, the type check and the tests on Home Assistant 2025.1, 2026.2 and 2026.10 on every push.

Versioning: `YEAR.MONTH.NN` (e.g. `2026.10.01`).
