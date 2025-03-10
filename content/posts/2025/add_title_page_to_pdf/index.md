---
title: "Script to Add a Title Page to PDFs"
date: 2025-03-10T12:30:20+08:00
draft: false
sidebar: false
comment: true
author: nand2mario
---

I've recently found myself frequently using the "ChatGPT to PDF" Chrome extension to convert ChatGPT conversations into PDF documents. The Deep Research discussions in particular contain valuable info worth preserving in ebook format. However they lack proper title pages. So here's a quick Python script to add a simple title page to PDF documents.

<!--more-->

`title4pdf.py`:

```python
import os
import tempfile
import subprocess
from fpdf import FPDF

def add_title_page(input_pdf, output_pdf, title, subtitle=None):
    # Create temporary title page PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
        # Create title page with fpdf2
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 24)
        
        # Calculate centered position for title
        pdf.cell(0, 40, text="", new_x="LMARGIN", new_y="NEXT")  # Add vertical spacing
        pdf.multi_cell(0, 10, text=title, align="C")
        
        # Add subtitle if provided
        if subtitle:
            pdf.set_font("Helvetica", "", 16)
            pdf.ln(10)  # Space between title and subtitle
            pdf.multi_cell(0, 10, text=subtitle, align="C")
        
        # Save temporary title page
        pdf.output(temp_pdf.name)
    
    try:
        # Merge PDFs using pdftk
        subprocess.run([
            "pdftk",
            temp_pdf.name,
            input_pdf,
            "cat",
            "output",
            output_pdf
        ], check=True)
    finally:
        # Clean up temporary file
        os.remove(temp_pdf.name)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add title page to PDF")
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("title", help="Title text")
    parser.add_argument("output", help="Output PDF file")
    parser.add_argument("--subtitle", help="Subtitle text (optional)")
    args = parser.parse_args()
    
    add_title_page(args.input, args.output, args.title, args.subtitle)
```
