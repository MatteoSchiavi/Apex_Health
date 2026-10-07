import SwiftUI

@main
struct ApexHealthBridgeApp: App {
    @StateObject private var model = BridgeModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                Form {
                    Section("Apex pairing") {
                        TextField("Apex server URL", text: $model.serverAddress)
                            .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                            .disabled(model.paired)
                        if !model.paired {
                            TextField("Device name", text: $model.deviceName)
                            SecureField("One-time code from Apex Settings", text: $model.pairingCode)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                            Button("Pair iPhone", action: model.pair)
                                .disabled(model.busy)
                            Text("Create a 10-minute pairing code while signed in to Apex on the web.")
                                .font(.footnote)
                        } else { Text("Device paired with a revocable HealthKit-only token.").font(.footnote) }
                    }
                    if model.paired {
                        Section("Apple Health") {
                            Button("Review read permissions", action: model.authorize).disabled(model.busy)
                            Button("Sync now", action: model.syncNow).disabled(model.busy)
                            Text("Initial backfill covers 90 days. Apple HRV is SDNN and retains its methodology.")
                                .font(.footnote)
                        }
                    }
                    Section("Sync status") {
                        Text(model.status)
                        if model.busy { ProgressView() }
                        if let date = model.lastSuccessAt {
                            LabeledContent("Last acknowledged upload") { Text(date, style: .relative) }
                        }
                        if let checkpoint = model.checkpoint { LabeledContent("Checkpoint", value: String(checkpoint)) }
                        if let error = model.errorMessage { Text(error).foregroundStyle(.red) }
                    }
                    Section("Troubleshooting and privacy") {
                        Text("iOS does not disclose whether individual read permissions were denied. Empty results can mean no data or denied access. Review Health → profile → Apps → Apex Health Bridge.")
                        Text("Background delivery is best effort, may be delayed, and may require opening the app after force quit or restart. Keep the app open during the first backfill.")
                        Text("Only permitted sample types and bounded source metadata are uploaded. The app cannot write to Apple Health and does not log health payloads. Local sync state stays on this device and is excluded from backups.")
                        Text("Revoking permissions stops access to those data. Revoke the device in Apex Settings to invalidate its sync token.")
                        if model.paired { Button("Remove local pairing", role: .destructive, action: model.disconnect).disabled(model.busy) }
                    }.font(.footnote)
                }
                .navigationTitle("Apex Health Bridge")
            }
            .onChange(of: scenePhase) { _, phase in model.becameActive(phase == .active) }
            .task { model.becameActive(scenePhase == .active) }
        }
    }
}
