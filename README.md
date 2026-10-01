# Kicad Parts Repository

## Source files

There are basically 3 directories **src/3dmodels**, **src/footprints**, **src/symbols** with sub-directories for categories, thats where the different parts of the library lives.

The different symbols should go into `src/symbols/<CATEGORY>.kicad_sym`

Add a datasheet 

```
└── src
    ├── 3dmodels
    │   ├── Modules.3dshapes
    │   ├── Optocouplers.3dshapes
    │   └── Switches.3dshapes
    ├── footprints
    │   ├── Modules.pretty
    │   ├── Optocouplers.pretty
    │   │   └── TLP2391.kicad_mod
    │   └── Switches.pretty
    └── symbols
        ├── Modules.kicad_sym
        ├── Optocouplers.kicad_sym
        └── Switches.kicad_sym
```

## Design guide lines

If possible try to keep in line with the [official Kicad guidelines](https://klc.kicad.org/), but they are not not enforced here