# Tech Sinum integráció Home Assistanthoz

Jelenleg az integráció **alfa fázisban** van, ezért **csak saját felelősségre** használd!

## Telepítés

Az integráció telepítése után csak az **IP címet** és a **token-t** kell megadnod.  
Az egyes entitások frissítési ideje az integrációhoz tartozó `.py` fájlokban módosítható.

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

## Korlátozások

- Az integráció még alfa fázisban van, ezért előfordulhatnak hibák.


---


# Tech Sinum Integration for Home Assistant

The integration is currently in the **alpha phase**, so **use it at your own risk**!

## Installation

After installing the integration, you only need to configure the **IP address** and **token**.  
The update interval for each entity domain can be modified in the corresponding `.py` files.

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

## Limitations

- The integration is still in the alpha phase, so bugs may occur.

---