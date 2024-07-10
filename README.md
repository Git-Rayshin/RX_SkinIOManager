# RX Skin IO Manager

RX Skin IO Manager is a skin weight management tool for Autodesk Maya.

This public version excludes components related to pymel, mGear, and all pipeline-related elements.

You should be able to run this tool in any Maya environment with numpy installed.

![maya2020](https://img.shields.io/badge/Maya_2020-tested-brightgreen.svg)
![maya2022](https://img.shields.io/badge/Maya_2022-tested-brightgreen.svg)
![maya2023](https://img.shields.io/badge/Maya_2023-tested-brightgreen.svg)
![maya2024](https://img.shields.io/badge/Maya_2024-tested-brightgreen.svg)

![numpy](https://img.shields.io/badge/numpy-required-red.svg)

![Windows](https://img.shields.io/badge/Windows-tested-blue)

<div style="text-align: center;">
    <img src="https://github.com/Git-Rayshin/RX_SkinIOManager/assets/115437984/4346936c-add7-4e14-b99a-cce8710b025b" alt="UIimage" height="500">
</div>



-------------------

## Manage your skin files in a more organized way!

- Simple version control(more stuff in full version)
- Allow you to save/load/track your skin/skinPack files
- Fast skin IO with numpy
- Easy to use UI

## Installation

Place the `skin_io_manager` directory in one of Maya's Python script directories.

Alternatively, add the directory of your choice to the PYTHONPATH environment variable, then place the `skin_io_manager`
directory in that directory.

## Usage

Launch the GUI by running the following:

```python
import skin_io_manager.ui as skinIO

skinIO.show(dock=False)
```

## Revisions

### 1.0.0

Initial release of RX Skin IO Manager

## Author

[Ruixin He](https://github.com/Git-Rayshin)

## License

MIT License
