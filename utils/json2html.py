#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2025 Cyril Hrubis <chrubis@suse.cz>
"""
This script parses JSON results from kirk and produces a HTML page.
"""
import os
import json
import argparse
from datetime import timedelta
from html import escape

_HTML_HEADER = """<html>
 <head>
  <meta charset=\"UTF-8\">
  <title>LTP results</title>
  <style>
   body {
    background-color: #eee;
    font: 80% \"Helvetica\";
    text-align: center;
   }
   table {border-collapse: collapse;}
   th, td {
    border-bottom: 1px solid #888;
    text-align: right;
    padding-top: 0.1em;
    padding-bottom: 0.1em;
    padding-left: 0.5em;
    padding-right: 0.5em;
   }
   th {
       border-top: 1px solid #888;
       background-color: #ccc;
   }
   tr {
       border-left: 1px solid #888;
       border-right: 1px solid #888;
   }
   hr {border-top: 1px solid #888; border-bottom: 0px;}
   td:hover.rtime {background-color: #ccf}
   td:hover.pass {background-color: #9f9}
   td:hover.fail {background-color: #f99}
   td:hover.brok {background-color: #f99}
   td:hover.skip {background-color: #ff9}
   td:hover.warn {background-color: #f9f}
   td.rtime {background-color: #aaf; text-align: center;}
   td.pass {background-color: #7f7; text-align: center;}
   td.fail {background-color: #f77; text-align: center;}
   td.brok {background-color: #f77; text-align: center;}
   td.skip {background-color: #ff7; text-align: center;}
   td.warn {background-color: #f7f; text-align: center;}
   th.id, td.id {text-align: left; width: 15em;}
   th:hover {background-color: #bbb}
   tr:hover.info {background-color: #eee}
   tr:hover.pass {background-color: #9f9}
   tr:hover.fail {background-color: #f99}
   tr:hover.brok {background-color: #f99}
   tr:hover.skip {background-color: #ff9}
   tr:hover.warn {background-color: #f9f}
   tr.info {background-color: #ddd; text-align: left;}
   tr.pass {background-color: #7f7}
   tr.fail {background-color: #f77}
   tr.brok {background-color: #f77}
   tr.skip {background-color: #ff7}
   tr.warn {background-color: #f7f}
   tr.hidden1 {display: none}
   tr.hidden2 {display: none}
   tr.hidden3 {display: none}
   tr.logs {background-color: #bbb;}
   tr:hover.logs {background-color: #ccc;}
   td.logs {text-align: left}
   table.hidden {display: none}
  </style>
  <script type=\"text/javascript\">
   function toggle_visibility(element, class_id) {
       var table = document.getElementById(\"results\");
       table.classList.add(\"hidden\");
       if (element.checked) {
           for (var i = 1; table.rows[i]; i+=2) {
               if (table.rows[i].classList.contains(class_id)) {
                   table.rows[i].classList.add(\"hidden1\");
                   table.rows[i+1].classList.add(\"hidden1\");
               }
           }
       } else {
           for (var i = 1; table.rows[i]; i+=2) {
               if (table.rows[i].classList.contains(class_id)) {
                   table.rows[i].classList.remove(\"hidden1\");
                   table.rows[i+1].classList.remove(\"hidden1\");
               }
           }
       }
       table.classList.remove(\"hidden\");
   }
   function filter_by_id(substr) {
       var table = document.getElementById(\"results\");
       table.classList.add(\"hidden\");
       for (var i = 1; table.rows[i]; i+=2) {
           if (table.rows[i].cells[0].innerText.includes(substr)) {
               table.rows[i].classList.remove(\"hidden2\");
               table.rows[i+1].classList.remove(\"hidden2\");
           } else {
               table.rows[i].classList.add(\"hidden2\");
               table.rows[i+1].classList.add(\"hidden2\");
           }
       }
       table.classList.remove(\"hidden\");
   }
   function cmp_asc(row1, row2, cell_id) {
       var h1 = row1.cells[cell_id].innerHTML;
       var h2 = row2.cells[cell_id].innerHTML;
       if (cell_id == 0) return h1 < h2
       return parseFloat(h1) < parseFloat(h2);
   }
   function cmp_desc(row1, row2, cell_id) {
       var h1 = row1.cells[cell_id].innerHTML;
       var h2 = row2.cells[cell_id].innerHTML;
       if (cell_id == 0) return h1 > h2
       return parseFloat(h1) > parseFloat(h2);
   }
   function sort(cmp, cell_id) {
       var table = document.getElementById(\"results\");
       table.classList.add(\"hidden\");
       for (var i = 3; table.rows[i]; i+=2) {
           var l = 1, r = i, m;
           while (r - l > 2) {
               /* Find odd table row in the middle */
               m = (r - l)/2 + l + ((((r - l)/2) % 2) ? 1 : 0);
               if (cmp(table.rows[i], table.rows[m], cell_id))
                   r = m;
               else
                   l = m;
           }
           m = cmp(table.rows[l], table.rows[i], cell_id) ? r : l;
           if (i == m)
               continue;
           var rowi1 = table.rows[i];
           var rowi2 = table.rows[i+1];
           var row = table.rows[m];
           rowi1.parentNode.insertBefore(rowi1, row);
           rowi2.parentNode.insertBefore(rowi2, row);
       }
       table.classList.remove(\"hidden\");
   }
   function sort_by(cell_id) {
       var table = document.getElementById(\"results\");
       var id_col = table.rows[0].cells[cell_id].innerHTML;
       if (id_col.endsWith(\"\\u2191\")) {
           sort(cmp_desc, cell_id);
           table.rows[0].cells[cell_id].innerHTML = id_col.slice(0, -1) + \"\\u2193\";
       } else {
           sort(cmp_asc, cell_id);
           table.rows[0].cells[cell_id].innerHTML = id_col.slice(0, -1) + \"\\u2191\";
       }
   }
  </script>
 </head>
 <body>
  <div style=\"display: inline-block\">
   <center>
   <h1>LTP Results</h1>"""

_HTML_FOOTER = """   </center>
  </div>
  <script type=\"text/javascript\">
   var table = document.getElementById(\"results\");
   for (var i = 1; table.rows[i]; i++) {
       table.rows[i].onclick = function() {
           if (this.classList.contains(\"logs\")) {
               this.classList.add(\"hidden3\");
           } else {
               var next_row = this.parentNode.rows[this.rowIndex + 1];
               if (next_row.classList.contains(\"hidden3\"))
                   next_row.classList.remove(\"hidden3\");
               else
                   next_row.classList.add(\"hidden3\");
           }
       }
   }
  </script>
 </body>
</html>"""


def _generate_environment(environment):
    """
    Generates HTML environment table.
    """
    out = []
    out.append("   <table width=\"100%\">")
    out.append("    <tr>")
    out.append("     <th colspan=\"2\" style=\"text-align: center\">Environment information</th>")
    out.append("    </tr>")

    print("\n".join(out))

    for key in environment:
        out = []

        out.append("    <tr class=\"info\">")
        out.append(f"     <td>{key}</td>")
        out.append(f"     <td>{environment[key]}</td>")
        out.append("    </tr>")

        print("\n".join(out))

    print("   </table>")


def _generate_stats(stats):
    """
    Generates HTML overall statistics.
    """

    out = []
    out.append("   <table width=\"100%\">")
    out.append("    <tr>")
    out.append("     <th colspan=\"6\" style=\"text-align: center\">Overall results</th>")
    out.append("    </tr>")
    out.append("    <tr>")
    out.append(f"     <td class=\"rtime\">Runtime: {str(timedelta(seconds=stats['runtime']))}</td>")
    out.append(f"     <td class=\"pass\">Passed: {stats['passed']}</td>")
    out.append(f"     <td class=\"skip\">Skipped: {stats['skipped']}</td>")
    out.append(f"     <td class=\"fail\">Failed: {stats['failed']}</td>")
    out.append(f"     <td class=\"brok\">Broken: {stats['broken']}</td>")
    out.append(f"     <td class=\"warn\">Warnings: {stats['warnings']}</td>")
    out.append("    </tr>")
    out.append("   </table>")

    print("\n".join(out))


_RESULT_TABLE_HEADER = """    <div style=\"background-color: #ccc\">
     <hr>
     <input type=\"checkbox\" onchange=\"toggle_visibility(this, 'pass')\"> Hide Passed
     <input type=\"checkbox\" onchange=\"toggle_visibility(this, 'skip')\"> Hide Skipped
     Filter by ID: <input type=\"text\" onkeyup=\"filter_by_id(this.value)\">
     <hr>
    </div>
    <table id=\"results\" style=\"cursor: pointer\">
     <tr>
      <th onclick=\"sort_by(0)\" class=\"id\">Test ID &#8597;</th>
      <th onclick=\"sort_by(1)\">Duration &#8597;</th>
      <th onclick=\"sort_by(2)\">Passes &#8597;</th>
      <th onclick=\"sort_by(3)\">Skips &#8597;</th>
      <th onclick=\"sort_by(4)\">Fails &#8597;</th>
      <th onclick=\"sort_by(5)\">Broken &#8597;</th>
      <th onclick=\"sort_by(6)\">Warns &#8597;</th>
     </tr>"""


def _generate_results(results):
    """
    generates html result table.
    """
    print(_RESULT_TABLE_HEADER)

    for res in results:
        overall = 'pass'

        test = res['test']

        if test['failed'] > 0:
            overall = 'fail'
        elif test['broken'] > 0:
            overall = 'brok'
        elif test['warnings'] > 0:
            overall = 'warn'
        elif test['skipped'] > 0:
            overall = 'skip'

        out = []

        out.append(f"     <tr class=\"{overall}\">")
        out.append(f"      <td class=\"id\">{res['test_fqn']}</td>")
        out.append(f"      <td>{test['duration']:.2f}</td>")
        out.append(f"      <td>{test['passed']}</td>")
        out.append(f"      <td>{test['skipped']}</td>")
        out.append(f"      <td>{test['failed']}</td>")
        out.append(f"      <td>{test['broken']}</td>")
        out.append(f"      <td>{test['warnings']}</td>")
        out.append("     </tr>")
        out.append("     <tr class=\"logs hidden3\">")
        out.append("      <td class=\"logs\" colspan=\"8\">")
        out.append("       <pre>")
        out.append(escape(test['log']) + "      </pre>")
        out.append("      </td>")
        out.append("     </tr>")

        print("\n".join(out))

    print("    </table>")


def _generate_html(results_path):
    """
    Generates HTML results.
    """
    print(_HTML_HEADER)

    with open(results_path, 'r', encoding="utf-8") as file:
        results = json.load(file)

    _generate_environment(results['environment'])
    _generate_stats(results['stats'])
    _generate_results(results['results'])

    print(_HTML_FOOTER)


def _file_exists(filepath):
    """
    Check if the given file path exists.
    """
    if not os.path.isfile(filepath):
        raise argparse.ArgumentTypeError(
            f"The file '{filepath}' does not exist.")
    return filepath


def run():
    """
    Entry point of the script.
    """
    parser = argparse.ArgumentParser(
        description="Script to generate simple HTML result table.")

    parser.add_argument(
        '-r',
        '--results',
        type=_file_exists,
        required=True,
        help='kirk results.json file location')

    args = parser.parse_args()

    _generate_html(args.results)


if __name__ == "__main__":
    run()
