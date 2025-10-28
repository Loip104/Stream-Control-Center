#!/usr/bin/env python3
"""
Kopiert alle msgid-Werte in die entsprechenden msgstr-Felder einer .po-Datei.
Nützlich um eine deutsche .po-Datei zu erstellen, wo msgid = msgstr.
"""

import sys
import re

def process_po_file(input_file, output_file):
    """
    Liest eine .po-Datei und kopiert msgid-Inhalte in leere msgstr-Felder.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    result = []
    current_msgid = None
    current_msgid_lines = []
    in_msgid = False
    in_msgstr = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Kommentare und leere Zeilen durchreichen
        if line.startswith('#') or line.strip() == '':
            result.append(line)
            i += 1
            continue
        
        # msgid gefunden
        if line.startswith('msgid '):
            in_msgid = True
            in_msgstr = False
            current_msgid_lines = [line]
            
            # Mehrzeilige msgid sammeln
            j = i + 1
            while j < len(lines) and lines[j].startswith('"'):
                current_msgid_lines.append(lines[j])
                j += 1
            
            # msgid-Zeilen zum Ergebnis hinzufügen
            result.extend(current_msgid_lines)
            i = j
            continue
        
        # msgstr gefunden
        if line.startswith('msgstr '):
            in_msgstr = True
            in_msgid = False
            
            # Prüfen ob msgstr leer ist
            if line.strip() == 'msgstr ""':
                # Leeres msgstr - kopiere msgid-Inhalt
                if current_msgid_lines:
                    for msgid_line in current_msgid_lines:
                        # Ersetze "msgid" durch "msgstr" in der ersten Zeile
                        msgstr_line = msgid_line.replace('msgid ', 'msgstr ', 1)
                        result.append(msgstr_line)
                else:
                    result.append(line)
            else:
                # msgstr hat bereits Inhalt - behalten
                result.append(line)
                # Mehrzeilige msgstr durchreichen
                j = i + 1
                while j < len(lines) and lines[j].startswith('"'):
                    result.append(lines[j])
                    j += 1
                i = j
                continue
            
            i += 1
            continue
        
        # Alle anderen Zeilen durchreichen
        result.append(line)
        i += 1
    
    # Ergebnis schreiben
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(result)
    
    print(f"✓ Erfolgreich! Deutsche .po-Datei erstellt: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Verwendung: python po_copy_msgid_to_msgstr.py <input.po> <output.po>")
        print("Beispiel:   python po_copy_msgid_to_msgstr.py messages.po messages_de.po")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    try:
        process_po_file(input_file, output_file)
    except FileNotFoundError:
        print(f"Fehler: Datei '{input_file}' nicht gefunden!")
        sys.exit(1)
    except Exception as e:
        print(f"Fehler beim Verarbeiten: {e}")
        sys.exit(1)