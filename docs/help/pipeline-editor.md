# Pipeline Editor

## Overview

The pipeline editor is the core workspace in Blueprint. It provides a visual canvas where you build ML experiments by placing blocks and connecting them into directed acyclic graphs (DAGs). Each pipeline represents a complete experiment workflow — from data loading through training to evaluation.

## Canvas Basics

The canvas is an infinite, pannable workspace. Use the following controls to navigate:

- **Pan:** Click and drag on empty canvas space, or use the scroll wheel with Shift held.
- **Zoom:** Scroll up/down to zoom in/out. The zoom level is shown in the bottom-right corner.
- **Fit to view:** Press **G** to toggle the guide overlay, which centers the canvas on your pipeline.
- **Select:** Click a block to select it. Hold **Shift** and click to add blocks to the selection.
- **Multi-select:** Click and drag on empty space to draw a selection rectangle.

## Adding Blocks

There are several ways to add blocks to the canvas:

1. **Block palette:** Open the left sidebar to browse available blocks organized by category. Drag a block from the palette onto the canvas.
2. **Command palette:** Press **Cmd+K** to open the command palette. Type a block name to search, then press Enter to place it.
3. **Templates:** Use pipeline templates to start with a pre-built arrangement of blocks. Templates are available from the File menu.

## Connecting Ports

Blocks expose input ports (left side) and output ports (right side). To connect two blocks:

1. Hover over an output port until it highlights.
2. Click and drag from the output port toward the target input port.
3. Release on a compatible input port to create the connection.

Ports are color-coded by data type:

| Color  | Type       | Description                   |
|--------|------------|-------------------------------|
| Blue   | DataFrame  | Tabular data (pandas)         |
| Green  | Tensor     | Numerical arrays / tensors    |
| Orange | Model      | Trained model objects          |
| Purple | Text       | String or text data            |
| Gray   | Any        | Accepts any compatible type    |

Incompatible ports will not accept a connection. If a connection is invalid, the port will flash red and the connection will be rejected.

## Block Configuration

Click on any block to open its configuration panel on the right side of the screen. The panel shows:

- **Block name:** Editable display name for the block instance.
- **Parameters:** Block-specific settings (e.g., learning rate, number of epochs, file paths).
- **Input/output summary:** Lists connected ports and their data types.
- **Documentation:** A brief description of what the block does and how to configure it.

Changes to block parameters are saved automatically when you click away or press **Cmd+S**.

## Pipeline Templates

Blueprint ships with several pipeline templates for common ML workflows:

- **Classification pipeline:** Dataset loader, train/test split, classifier, evaluation.
- **Regression pipeline:** Dataset loader, feature engineering, regressor, metrics.
- **NLP pipeline:** Text loader, tokenizer, embedding, model training, evaluation.
- **Custom:** Start from a blank canvas.

Access templates from **File > New from Template** or when creating a new pipeline.

## Validation

Blueprint continuously validates your pipeline as you edit:

- **Missing connections:** Required input ports that have no incoming connection are flagged with a warning icon.
- **Type mismatches:** Connections between incompatible port types are highlighted in red.
- **Cycles:** The pipeline must be a DAG. Cycles are detected and flagged immediately.
- **Missing configuration:** Blocks with required parameters that are not set show a yellow warning badge.

You can also run a full validation manually with **Cmd+S**, which checks all of the above and reports any issues in the status bar.

## Undo and Redo

All canvas operations support undo/redo:

- **Undo:** Cmd+Z
- **Redo:** Cmd+Shift+Z

This covers block placement, deletion, connection changes, and parameter edits.

## Keyboard Shortcuts in the Editor

| Shortcut       | Action                        |
|----------------|-------------------------------|
| Cmd+S          | Save pipeline                 |
| Cmd+Z          | Undo                          |
| Cmd+Shift+Z    | Redo                          |
| Cmd+K          | Open command palette          |
| Delete/Backspace | Delete selected block(s)    |
| G              | Toggle guide overlay          |
| Cmd+A          | Select all blocks             |

## Tips

- Double-click a block to jump directly to its configuration.
- Right-click a block to access context menu options: duplicate, delete, view documentation.
- Hold **Alt** while dragging a block to duplicate it.
- Use **Cmd+Shift+C** to clone the entire pipeline for experimentation.
