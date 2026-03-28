# Viewing Results

## Results View

After a pipeline run completes, switch to the Results view by pressing **Cmd+6** or clicking **Results** in the sidebar. The results view shows a comprehensive summary of the run.

## Metrics

The metrics panel displays scalar values produced by evaluation blocks:

- Accuracy, precision, recall, F1 score.
- Loss values (training and validation).
- Custom metrics defined in your evaluation blocks.

Metrics are displayed as cards with the metric name, value, and a small trend indicator if previous runs exist for comparison.

### Comparing Metrics Across Runs

Select multiple runs from the run history to compare their metrics side by side. Blueprint shows a comparison table highlighting improvements and regressions.

## Outputs

The outputs panel shows the data produced by each block in the pipeline:

- **DataFrames** are displayed in an interactive data grid (sortable, filterable columns).
- **Tensors** are shown as shape summaries with the option to expand and inspect values.
- **Models** display metadata: framework, parameter count, training metrics.
- **Text** outputs are rendered in a scrollable text area.
- **Images** are displayed inline with zoom support.

Click on any block in the results tree to view its specific outputs.

## Data Grid

When a block outputs a DataFrame, the data grid provides:

- **Sorting:** Click column headers to sort ascending or descending.
- **Filtering:** Use the filter row to narrow rows by value or range.
- **Column resizing:** Drag column borders to adjust width.
- **Pagination:** Large datasets are paginated. Use the controls at the bottom to navigate pages.
- **Search:** Type in the search bar to find rows matching a keyword across all columns.

The data grid displays up to 10,000 rows by default. For larger datasets, use the export function to download the full output.

## Charts and Visualizations

Blueprint automatically generates charts for common output types:

- **Loss curves:** Training and validation loss over epochs.
- **Confusion matrix:** Heatmap for classification results.
- **ROC curve:** Receiver operating characteristic for binary classifiers.
- **Distribution plots:** Histograms for numerical columns in DataFrames.
- **Scatter plots:** For two-column outputs or predicted vs actual values.

Charts are interactive — hover for tooltips, click to zoom, drag to pan.

### Custom Charts

Evaluation blocks can specify custom chart configurations in their output. The chart specification follows a simple format:

```python
return {
    "metrics": {"accuracy": 0.95},
    "charts": [
        {
            "type": "line",
            "title": "Training Loss",
            "x": epoch_list,
            "y": loss_list,
            "xlabel": "Epoch",
            "ylabel": "Loss",
        }
    ],
}
```

## Export

Export results in several formats:

- **CSV:** Export DataFrames as CSV files.
- **JSON:** Export structured data and metrics as JSON.
- **PNG/SVG:** Export charts as image files.
- **Report:** Generate a full HTML report combining metrics, charts, and data summaries.

Access export options from the **Export** button in the results toolbar or by right-clicking specific outputs.

## Artifacts

Run artifacts are stored in `~/.specific-labs/artifacts/{run_id}/`. Each block's output is saved as a separate file. Artifacts include:

- Serialized model files (.pkl, .pt, .onnx).
- Output DataFrames (.parquet).
- Generated images and charts.
- Log files and metadata.

Artifacts are preserved across sessions and can be referenced from other pipelines.

## System Metrics

During a run, Blueprint records system resource usage:

- CPU utilization over time.
- Memory consumption per block.
- GPU utilization (if available).
- Total run duration and per-block timing.

View these in the **Monitor** tab alongside the results to identify performance bottlenecks.

## Tips

- Use the comparison view to track experiment progress across multiple runs.
- Pin important metrics to the project dashboard for quick reference.
- Export reports when sharing results with collaborators.
- Check system metrics to identify blocks that could benefit from GPU acceleration or optimization.
