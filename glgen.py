
import xml.etree.ElementTree as ET
import argparse
from packaging import version

parser = argparse.ArgumentParser()
parser.add_argument('spec_file', help='path to spec xml file')

args = parser.parse_args()

root = ET.parse(args.spec_file).getroot()

print("#pragma once")
print()
print("// GENERATED")
print()
print(
    '#if defined(_WIN32) && !defined(APIENTRY) && !defined(__CYGWIN__) && !defined(__SCITECH_SNAP__)',
    '#ifndef WIN32_LEAN_AND_MEAN',
    '#define WIN32_LEAN_AND_MEAN 1',
    '#endif',
    '#include <windows.h>',
    '#endif',
    '',
    '#ifndef APIENTRY',
    '#define APIENTRY',
    '#endif',
    '#ifndef APIENTRYP',
    '#define APIENTRYP APIENTRY *',
    '#endif',
    '#ifndef GLAPI',
    '#define GLAPI extern',
    '#endif', sep="\n")

print()

types_requires = {}
types = {}
enums = {}
commands_ptypes = {}
commands = {}

for types_node in root.findall('types'):
    for type_node in types_node:
        assert(type_node.tag == "type")
        if "name" in type_node.attrib:
            name = type_node.attrib["name"]
        else:
            name_node = type_node.find("name")
            name = name_node.text

        text = ""
        for node in type_node.iter():
            text += node.text if node.text is not None else ""
            text += node.tail.strip() if node.tail is not None else ""

        types[name] = text
        types_requires[name] = type_node.attrib["requires"] if "requires" in type_node.attrib else None

for enums_node in root.findall('enums'):
    for enum_node in enums_node:
        assert(enum_node.tag == "enum" or enum_node.tag == "unused")

        if "name" in enum_node.attrib:
            name = enum_node.attrib["name"]
            enums[name] = enum_node.attrib["value"] + (enum_node.attrib["type"] if "type" in enum_node.attrib else "")
        else:
            assert(enum_node.tag == "unused")

for commands_node in root.findall('commands'):
    for command_node in commands_node:
        assert(command_node.tag == "command")
        name = None
        text = "typedef "
        firstNode = True
        firstParam = True
        for command_def_node in command_node:
            if firstNode:
                assert(command_def_node.tag == "proto")
                firstNode = False

                text += "".join(command_def_node.itertext())

                for node in command_def_node.iter():
                    if node.tag == "name":
                        text = text.replace(node.text.strip(), "(APIENTRYP PFN" + node.text.upper() + "PROC)")
                        name = node.text.strip()
                        commands_ptypes[name] = []

                text += " ("

            else:
                assert(command_def_node.tag == "param" or command_def_node.tag == "alias" or command_def_node.tag == "vecequiv" or command_def_node.tag == "glx")

                if command_def_node.tag == "param":
                    if firstParam:
                        firstParam = False
                    else:
                        text += ", "

                    text += "".join(command_def_node.itertext())

                    for node in command_def_node.iter():
                        if (node.tag == "ptype"):
                            commands_ptypes[name].append(node.text)

        text += ");"

        commands[name] = text


apis = { "gl": "1.0", "gles2": "2.0" }

for current_api in apis:
    required_types = []
    required_enums = []
    required_enums_per_version = {}
    required_commands = []
    required_commands_per_version = {}

    for feature_node in root.findall('feature'):
        if feature_node.attrib['api'] == current_api:
            for action_node in feature_node:
                assert(action_node.tag == "require" or action_node.tag == "remove")

                if action_node.tag == "require":
                    for elmt in action_node:
                        assert(elmt.tag == "type" or elmt.tag == "enum" or elmt.tag == "command")

                        if elmt.tag == "type":
                            assert(elmt.attrib["name"] not in required_types)
                            required_types.append(elmt.attrib["name"])
                        elif elmt.tag == "enum":
                            if elmt.attrib["name"] not in required_enums:
                                required_enums.append(elmt.attrib["name"])
                        elif elmt.tag == "command":
                            if elmt.attrib["name"] not in required_commands:
                                required_commands.append(elmt.attrib["name"])

                elif action_node.tag == "remove":
                    assert(feature_node.attrib['number'] == "3.2")
                    for elmt in action_node:
                        assert(elmt.tag == "type" or elmt.tag == "enum" or elmt.tag == "command")

                        if elmt.tag == "type":
                            required_types.remove(elmt.attrib["name"])
                        elif elmt.tag == "enum":
                            required_enums.remove(elmt.attrib["name"])
                        elif elmt.tag == "command":
                            required_commands.remove(elmt.attrib["name"])

                required_enums_per_version[feature_node.attrib['number']] = required_enums.copy()
                required_commands_per_version[feature_node.attrib['number']] = required_commands.copy()

    def add_required_types_recurse(type):
        requires = types_requires[type]
        if requires != None and requires not in required_types:
            required_types.append(requires)
            add_required_types_recurse(requires)

    for command in required_commands:
        for ptype in commands_ptypes[command]:
            required_types.append(ptype)
            add_required_types_recurse(ptype)

    for type in required_types:
        add_required_types_recurse(type)

    for type in types:
        if type in required_types:
            print(types[type])

    print()

    for command in required_commands:
        print(commands[command])

    print()

    previous_struct_name = None
    previous_version = None
    for v in required_commands_per_version:
        if version.parse(v) >= version.parse(apis[current_api]):
            if current_api == "gl":
                print("// OpenGL Core "+ v)
                struct_name = "GL_"+ str(v).replace(".", "_")
            else:
                print("// OpenGL ES "+ v)
                struct_name = "GL_ES_"+ str(v).replace(".", "_")
            if previous_struct_name is not None:
                print("struct", struct_name, ": public", previous_struct_name)
            else:
                print("struct", struct_name)
            print("{")

            if current_api == "gl" and version.parse(v) < version.parse("3.2"):

                for enum in required_enums_per_version[v]:
                    if enum in required_enums_per_version["3.2"]:
                        if previous_version is None or enum not in required_enums_per_version[previous_version]:
                            assert(enum.startswith("GL_"))
                            if enums[enum].endswith("u"):
                                print("\tstatic constexpr GLuint "+ enum[len("GL_"):] +" = "+ enums[enum] +";")
                            elif enums[enum].endswith("ull"):
                                print("\tstatic constexpr GLuint64 "+ enum[len("GL_"):] +" = "+ enums[enum] +";")
                            else:
                                print("\tstatic constexpr GLenum "+ enum[len("GL_"):] +" = "+ enums[enum] +";")

                print()

                for command in required_commands_per_version[v]:
                    if command in required_commands_per_version["3.2"]:
                        if previous_version is None or command not in required_commands_per_version[previous_version]:
                            assert(command.startswith("gl"))
                            print("\tPFN"+ command.upper() +"PROC", command[len("gl"):] +";")
                    #else:
                    #    assert(command.startswith("gl"))
                    #    print("\t//void *", command.lstrip("gl") +";")

            else:

                for enum in required_enums_per_version[v]:
                    if previous_version is None or enum not in required_enums_per_version[previous_version]:
                        assert(enum.startswith("GL_"))
                        if enums[enum].endswith("u"):
                            print("\tstatic constexpr GLuint "+ enum[len("GL_"):] +" = "+ enums[enum] +";")
                        elif enums[enum].endswith("ull"):
                            print("\tstatic constexpr GLuint64 "+ enum[len("GL_"):] +" = "+ enums[enum] +";")
                        else:
                            print("\tstatic constexpr GLenum "+ enum[len("GL_"):] +" = "+ enums[enum] +";")

                print()

                for command in required_commands_per_version[v]:
                    if previous_version is None or command not in required_commands_per_version[previous_version]:
                        assert(command.startswith("gl"))
                        print("\tPFN"+ command.upper() +"PROC", command[len("gl"):] +";")

            print("};")
            print()
            previous_struct_name = struct_name
            previous_version = v

print("enum OPENGL_VERSION")
print("{")

print("\tOPENGL_VERSION_UNKNOWN,")

print("\tOPENGL_VERSION_3_1,")

print("\tOPENGL_VERSION_3_2_CORE,")
print("\tOPENGL_VERSION_3_3_CORE,")
print("\tOPENGL_VERSION_4_0_CORE,")
print("\tOPENGL_VERSION_4_1_CORE,")
print("\tOPENGL_VERSION_4_2_CORE,")
print("\tOPENGL_VERSION_4_3_CORE,")
print("\tOPENGL_VERSION_4_4_CORE,")
print("\tOPENGL_VERSION_4_5_CORE,")
print("\tOPENGL_VERSION_4_6_CORE,")

print("\tOPENGL_VERSION_2_0_ES,")
print("\tOPENGL_VERSION_3_0_ES,")
print("\tOPENGL_VERSION_3_1_ES,")
print("\tOPENGL_VERSION_3_2_ES,")

print("};")
print()




