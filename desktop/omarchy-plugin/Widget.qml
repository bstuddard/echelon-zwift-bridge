// SPDX-License-Identifier: GPL-3.0-only
// Omarchy integration patterns: see the accompanying third-party notices.
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "local.echelon-bridge"
  readonly property string controlCommand: Quickshell.env("HOME") + "/.local/bin/echelon-bridge-control"
  property var bridgeStatus: ({ phase: "off", running: false, reachable: false, message: "Checking bridge status" })
  readonly property bool busy: actionProcess.running
  readonly property color statusColor: {
    if (busy || bridgeStatus.phase === "starting" || bridgeStatus.phase === "waiting") return "#e5b566"
    if (bridgeStatus.phase === "running" || bridgeStatus.phase === "external") return "#a5c980"
    if (bridgeStatus.phase === "error") return "#eb8e88"
    return bar ? bar.foreground : "#999999"
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (!statusProcess.running && !root.busy) statusProcess.running = true
  }

  function execute(action) {
    if (root.busy) return
    actionProcess.command = [root.controlCommand, action]
    actionProcess.running = true
  }

  IpcHandler {
    target: "local.echelon-bridge"
    function status(): string { return JSON.stringify(root.bridgeStatus) }
    function refresh(): void { root.broadcast("refresh") }
  }

  Process {
    id: statusProcess
    command: [root.controlCommand, "status-json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.bridgeStatus = JSON.parse(text) }
        catch (error) { root.bridgeStatus = ({ phase: "error", message: "Could not read bridge status" }) }
      }
    }
  }

  Process {
    id: actionProcess
    onExited: function(exitCode) { root.refresh() }
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf206"
    slotSize: Style.bar.statusSlot
    foreground: root.statusColor
    dimmed: root.bridgeStatus.phase === "off"
    pressable: !root.busy
    tooltipText: "Echelon Bridge — " + (root.busy ? "Working…" : root.bridgeStatus.message)
      + "\nLeft-click: start / open dashboard\nRight-click: stop bridge"
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) root.execute("stop")
      else if (mouseButton === Qt.LeftButton || mouseButton === Qt.MiddleButton) root.execute("open")
    }
  }
}
