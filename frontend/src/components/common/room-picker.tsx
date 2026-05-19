import { ComboboxField } from "@/components/common/combobox-field"
import type { RelocateRoom } from "@/shell/supervisor/hooks/use-decisions"

// Spec §10 — a thin selectable list over the existing `combobox-field` for
// the relocate `eligible_rooms`. It emits the chosen `new_room_id` (the
// `edit` payload key per §8). No new primitive, no new behaviour — purely a
// re-shaping of `RelocateRoom[]` into the combobox `ComboOption` contract.
export function RoomPicker({
  rooms,
  value,
  onChange,
}: {
  rooms: RelocateRoom[]
  value: string | null
  onChange: (newRoomId: string) => void
}) {
  const options = rooms.map((r) => ({ value: r.id, label: r.label }))
  return (
    <ComboboxField
      options={options}
      value={value}
      onChange={onChange}
      placeholder="Pick an eligible room…"
      emptyText="No eligible rooms"
    />
  )
}
