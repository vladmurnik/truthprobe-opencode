import pathlib, sys

p = pathlib.Path("/home/adik/src/opencode/packages/client/src/solid/data.ts")
src = p.read_text()

old = """      case "session.text.ended":
        message.editText(event.data.sessionID, event.data.assistantMessageID, (text) => {
          text.text = event.data.text
        })
        return
"""

new = """      case "session.text.ended":
        message.editText(event.data.sessionID, event.data.assistantMessageID, (text) => {
          text.text = event.data.text
          // truthprobe: durable confidence metadata published with the finished text
          if (event.data.truthprobe !== undefined) text.truthprobe = event.data.truthprobe
        })
        return
"""

if old not in src:
    print("ANCHOR NOT FOUND")
    sys.exit(1)

p.write_text(src.replace(old, new, 1))
print("patched", p)
