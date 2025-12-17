# Weather Code Lab

This repo contains code that goes with videos associated with the [Weather Code Lab](https://www.youtube.com/@WeatherCodeLab) YouTube channel.



## Threaded File Splitter

- Purpose: Split a large newline-delimited text file into N chunks concurrently while preserving line boundaries.
- Code: see [split_text_threaded.py](split_text_threaded.py)

### Quick Start

Run the demo (uses `metar.txt` if present, otherwise `data.txt`):

```bash
python test.py
```

Or call the function directly in your own script:

```python
from split_text_threaded import split_file_by_size_threaded

outputs = split_file_by_size_threaded(
	input_path="metar.txt",
	num_parts=4,
	output_dir="splits",
)
print(outputs)
```


