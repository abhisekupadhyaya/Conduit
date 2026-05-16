import { useState, type KeyboardEvent } from "react"
import { XIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"

// Controlled chip set for StaffSkill — the one sanctioned replace-set
// entity (spec §4). This is presentational only: the parent owns the
// `string[]` and calls the PUT replace-set hook on save (a later task).
export function SkillsField({
  value, onChange, placeholder = "Add a skill and press Enter",
}: {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}) {
  const [draft, setDraft] = useState("")

  function add() {
    const s = draft.trim()
    if (!s) return
    if (!value.includes(s)) onChange([...value, s])
    setDraft("")
  }

  function remove(skill: string) {
    onChange(value.filter((v) => v !== skill))
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault()
      add()
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      remove(value[value.length - 1])
    }
  }

  return (
    <div className="space-y-2">
      <Input
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
      />
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((skill) => (
            <Badge key={skill} variant="outline" className="gap-1 pr-1">
              {skill}
              <button
                type="button"
                aria-label={`Remove ${skill}`}
                className="text-muted-foreground hover:text-foreground rounded-sm"
                onClick={() => remove(skill)}
              >
                <XIcon className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}
