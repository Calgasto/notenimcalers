# Valls Data Explorer

Base mínima per:

- descarregar datasets CSV des de `https://dadesobertes.valls.cat`
- guardar-los en local a `data/raw/`
- generar un catàleg navegable a `data/catalog.json`
- generar un índex de transparència a `data/transparency_index.json`
- exposar una web estàtica centrada en despesa, departaments, contractes i ajuts
- buscar per empresa, beneficiari, departament o organisme i obrir el detall de tots els seus registres

## Sincronitzar dades

```bash
python3 scripts/sync_valls_data.py
```

Aquest comandament:

- descarrega i actualitza els CSV
- regenera `data/catalog.json`
- regenera `data/transparency_index.json`
- manté els fitxers derivats necessaris per a la web

Opcionalment:

```bash
python3 scripts/sync_valls_data.py --limit 5
```

## Obrir la web

```bash
python3 -m http.server 8000
```

Després obre `http://localhost:8000`.
