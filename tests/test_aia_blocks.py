"""
Test: Validate AIA BKY block definitions against known valid App Inventor blocks.

Ensures the Screen1.bky uses only real BluetoothClient/Notifier methods,
valid block types, and consistent global variable references.
"""
import xml.etree.ElementTree as ET
import os
import sys
import zipfile
import shutil
import tempfile

AIA_PATH = os.path.join(os.path.dirname(__file__), '..', 'android', 'Robotic_Arm_Control.aia')
AIA_PATH = os.path.abspath(AIA_PATH)

# Default Blockly namespace
NS = 'https://developers.google.com/blockly/xml'

def extract_bky(aia_path):
    """Extract Screen1.bky from the AIA zip file."""
    if not os.path.isfile(aia_path):
        raise FileNotFoundError(f"AIA file not found: {aia_path}")
    
    tmpdir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(aia_path) as z:
            bky_rel = 'src/appinventor/ai_rojasjhoansebastian17/Robotic_Arm_Control/Screen1.bky'
            z.extract(bky_rel, tmpdir)
            bky_path = os.path.join(tmpdir, bky_rel)
            with open(bky_path) as f:
                return f.read()
    finally:
        shutil.rmtree(tmpdir)

VALID_BLOCK_TYPES = {
    'component_event', 'component_method', 'component_set_get',
    'controls_if', 'global_declaration',
    'lexical_variable_get', 'lexical_variable_set', 'local_declaration_statement',
    'logic_boolean', 'logic_compare', 'logic_false', 'logic_true',
    'math_number', 'math_round', 'math_compare',
    'procedures_callnoreturn', 'procedures_defnoreturn',
    'text', 'text_join', 'text_segment', 'text_changeCase', 'text_contains',
}

VALID_BT_METHODS = {
    'Available', 'BytesAvailableToReceive', 'Connect', 'ConnectWithUUID',
    'Disconnect', 'IsConnected', 'IsDevicePaired',
    'ReceiveText', 'ReceiveSigned1ByteNumber', 'ReceiveSigned2ByteNumber',
    'ReceiveSigned4ByteNumber', 'ReceiveSignedBytes',
    'ReceiveUnsigned1ByteNumber', 'ReceiveUnsigned2ByteNumber',
    'ReceiveUnsigned4ByteNumber', 'ReceiveUnsignedBytes',
    'Send1ByteNumber', 'Send2ByteNumber', 'Send4ByteNumber',
    'SendBytes', 'SendText', 'StopAccepting',
}

VALID_NOTIFIER_METHODS = {
    'ShowTextDialog', 'ShowAlert', 'ShowChooseDialog',
    'ShowPasswordDialog', 'ShowTextInput',
}

VALID_BT_GET_PROPS = {
    'AddressesAndNames', 'Available', 'BytesAvailableToReceive',
    'CharacterEncoding', 'DelimiterByte', 'Enabled', 'HighByteFirst',
    'IsConnected', 'Secure',
}
VALID_BT_SET_PROPS = {'CharacterEncoding', 'DelimiterByte', 'HighByteFirst', 'Secure'}
VALID_LABEL_PROPS = {
    'BackgroundColor', 'FontBold', 'FontItalic', 'FontSize', 'FontTypeface',
    'HTMLContent', 'ShowFeedback', 'Text', 'TextAlignment', 'TextColor',
    'Visible', 'Width', 'Height',
}
VALID_LISTPICKER_PROPS = {
    'Elements', 'Selection', 'SelectionIndex', 'Items', 'Pictures',
}
VALID_CLOCK_SET_PROPS = {'TimerEnabled', 'TimerInterval'}

MUTATION_NS = 'http://www.w3.org/1999/xhtml'

def check_validator(bky_text):
    issues = []

    root = ET.fromstring(bky_text)

    for elem in root.iter():
        blk_type = elem.get('type')
        if blk_type and blk_type not in VALID_BLOCK_TYPES:
            issues.append(f"Unknown block type: {blk_type}")

    for mutation in root.iter(f'{{{MUTATION_NS}}}mutation'):
        comp_type = mutation.get('component_type')
        method_name = mutation.get('method_name')
        if comp_type == 'BluetoothClient' and method_name:
            if method_name not in VALID_BT_METHODS:
                issues.append(f"Invalid BluetoothClient method: {method_name}")
        if comp_type == 'Notifier' and method_name:
            if method_name not in VALID_NOTIFIER_METHODS:
                issues.append(f"Invalid Notifier method: {method_name}")

    for blk in root.iter(f'{{{NS}}}block'):
        if blk.get('type') != 'component_set_get':
            continue
        mutation = blk.find(f'{{{MUTATION_NS}}}mutation')
        if mutation is None:
            continue
        comp_type = mutation.get('component_type')
        prop = mutation.get('property_name')
        sg = mutation.get('set_or_get')

        if comp_type == 'BluetoothClient':
            allowed = VALID_BT_GET_PROPS if sg == 'get' else VALID_BT_SET_PROPS
            if prop not in allowed:
                issues.append(f"Invalid BluetoothClient {sg} property: {prop}")
        if comp_type == 'Label':
            if prop not in VALID_LABEL_PROPS:
                issues.append(f"Invalid Label {sg} property: {prop}")
        if comp_type == 'ListPicker':
            if prop not in VALID_LISTPICKER_PROPS:
                issues.append(f"Invalid ListPicker {sg} property: {prop}")
        if comp_type == 'Clock' and sg == 'set':
            if prop not in VALID_CLOCK_SET_PROPS:
                issues.append(f"Invalid Clock set property: {prop}")

    globals_declared = set()
    for blk in root.iter(f'{{{NS}}}block'):
        if blk.get('type') == 'global_declaration':
            name = blk.find(f'{{{NS}}}field[@name="NAME"]')
            if name is not None:
                globals_declared.add(name.text)

    globals_read = set()
    globals_written = set()
    for blk in root.iter(f'{{{NS}}}block'):
        f = blk.find(f'{{{NS}}}field[@name="VAR"]')
        if f is None or not f.text or not f.text.startswith('global '):
            continue
        gname = f.text[7:]
        if blk.get('type') == 'lexical_variable_get':
            globals_read.add(gname)
        elif blk.get('type') == 'lexical_variable_set':
            globals_written.add(gname)

    for g in (globals_read - globals_declared):
        issues.append(f"Global variable read but never declared: {g}")
    for g in (globals_written - globals_declared):
        issues.append(f"Global variable written but never declared: {g}")

    return issues

def test_extraction():
    assert os.path.isfile(AIA_PATH), f"AIA not found at {AIA_PATH}"
    bky = extract_bky(AIA_PATH)
    assert 'xmlns="https://developers.google.com/blockly/xml"' in bky, "Not a valid BKY"
    assert 'DiscardText' not in bky, "DiscardText block found (invalid method)"
    print(f"  BKY extracted OK ({len(bky)} bytes)")

def test_valid_blocks():
    bky = extract_bky(AIA_PATH)
    issues = check_validator(bky)
    assert not issues, f"Block validation failed:\n" + "\n".join(f"  - {i}" for i in issues)
    print(f"  All blocks validated OK")

def test_no_discardtext():
    bky = extract_bky(AIA_PATH)
    assert 'DiscardText' not in bky, "DiscardText must not appear in BKY"
    assert bky.count('method_name="DiscardText"') == 0
    print(f"  No DiscardText blocks: OK")

def test_isconnected_logic():
    bky = extract_bky(AIA_PATH)
    root = ET.fromstring(bky)
    writes = 0
    reads = 0
    for blk in root.iter(f'{{{NS}}}block'):
        f = blk.find(f'{{{NS}}}field[@name="VAR"]')
        if f is not None and f.text == 'global isConnected':
            if blk.get('type') == 'lexical_variable_set':
                writes += 1
            elif blk.get('type') == 'lexical_variable_get':
                reads += 1

    assert writes >= 1, f"Expected >=1 isConnected writes, got {writes}"
    assert reads >= 1, f"Expected >=1 isConnected reads, got {reads}"
    print(f"  isConnected: {reads} reads, {writes} writes")

def test_scm_checkresponse_disabled():
    """Verify CheckResponse clock has TimerEnabled=False in SCM."""
    import zipfile, tempfile, shutil
    import json

    tmpdir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(AIA_PATH) as z:
            scm_rel = 'src/appinventor/ai_rojasjhoansebastian17/Robotic_Arm_Control/Screen1.scm'
            z.extract(scm_rel, tmpdir)
            with open(os.path.join(tmpdir, scm_rel)) as f:
                scm_text = f.read()
    finally:
        shutil.rmtree(tmpdir)

    assert '"TimerEnabled":"False"' in scm_text, \
        "CheckResponse TimerEnabled must be False"
    print(f"  CheckResponse TimerEnabled=False: OK")

def test_all():
    test_extraction()
    test_valid_blocks()
    test_no_discardtext()
    test_isconnected_logic()
    test_scm_checkresponse_disabled()
    print("\nAll tests PASSED!")

if __name__ == '__main__':
    test_all()
