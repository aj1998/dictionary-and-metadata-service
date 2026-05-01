## JainKosh Page Structure With Selectors

### References format
The text contained in b/w <span class="GRef"> and </span> is a reference (remove any links if there inside)

### Structure
- Two Definitions:
    1. after `#सिद्धांतकोष_से` selector - first `#mw-content-text > div > p.HindiText` selector (nullable)
    2. after `#पुराणकोष_से` selector - first `#mw-content-text > div > div > p` selector (nullable, can contain links)

### Headings
- Create a node for each heading (even if it is incomplete)
- Merge heading text till final text appears to create topic
- Specify node as end node if no outgoing links
- If देखें link, then create graph link

### Text
- Each text as different document or json in a document.
- Sanskrit/Prakrit text to store in a separate field if available.
- Tables also in different format.