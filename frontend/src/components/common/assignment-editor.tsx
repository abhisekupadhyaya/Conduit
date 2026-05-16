import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { LockIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  ComboboxField, type ComboOption,
} from "@/components/common/combobox-field"
import { toast } from "sonner"

// For use inside the Rosters side-Sheet. Backend contract
// (supervisor/schemas/roster.py): create = POST CreateAssignmentIn
// {account_id, section_id?, assignment}; edit = PATCH PatchAssignmentIn
// {section_id?, assignment?, status?}. This component OWNS its form state
// and exposes Promise-returning, backend-shaped submit callbacks with a
// 409/422-aware toast.error catch — cloned from the sibling form-dialogs
// (staff-profile-form-dialog / roster-window-form-dialog, themselves
// cloned from issue-code-form-dialog). The mutation is supplied by the
// Task 12 page hook as a prop; this stays presentational + callback.
//
// The D12/D18 rule is taught in-UI (the issue-codes "lock is taught"
// precedent — tooltip + inline helper, never a silent disable):
//   - D18: an engineering account is skill-matched, not section-pooled —
//     Section is disabled with a taught tooltip and forced null.
//   - D12: owner/backup carries positional accountability — Section is
//     required with an inline helper (zod rejects "no section").
// section_id is nullable in both schemas (a member legitimately has no
// section; an assignment edited owner→member must drop it) so Section
// carries an explicit "— No section —" sentinel mapped to null, since a
// Radix SelectItem cannot hold an empty value.

const ROLES = ["owner", "backup", "member"] as const
const NO_SECTION = "__none__"

const schema = z
  .object({
    account_id: z.string().min(1, "Select a servicer"),
    section_id: z.string().nullable(),
    assignment: z.enum(ROLES),
  })
  .refine(
    // D12: owner/backup carries positional accountability — a section is
    // required. The "— No section —" sentinel maps to null and must NOT
    // satisfy this (mirrors the server 422). Engineering forces null but
    // is never owner/backup-with-required here (D18 clears section).
    (v) =>
      !(
        (v.assignment === "owner" || v.assignment === "backup") &&
        !v.section_id
      ),
    {
      message: "owner/backup carries section accountability — a section is required (D12)",
      path: ["section_id"],
    },
  )
type Form = z.infer<typeof schema>

export type ServicerOption = ComboOption & { staff_class: string }

export type AssignmentEdit = {
  id: string
  account_id: string
  section_id: string | null
  assignment: string
}

export function AssignmentEditor({
  servicers, sections, edit, onCreate, onPatch, submitLabel,
}: {
  servicers: ServicerOption[]
  sections: ComboOption[]
  // Edit path: an existing assignment row (Task 12 disables rows via the
  // existing Confirm, so this only needs section/role re-shaping).
  edit?: AssignmentEdit
  onCreate?: (payload: {
    account_id: string
    section_id: string | null
    assignment: string
  }) => Promise<unknown>
  onPatch?: (payload: {
    id: string
    section_id?: string | null
    assignment?: string
    status?: string
  }) => Promise<unknown>
  submitLabel?: string
}) {
  const isEdit = !!edit
  const { handleSubmit, reset, control, watch,
    formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: edit
      ? {
          account_id: edit.account_id,
          section_id: edit.section_id,
          assignment: edit.assignment as Form["assignment"],
        }
      : { account_id: "", section_id: null, assignment: "member" },
  })

  const accountId = watch("account_id")
  const picked = servicers.find((s) => s.value === accountId)
  const isEngineering = picked?.staff_class === "engineering"
  // D18: engineering is skill-matched, not section-pooled.
  const sectionDisabled = isEngineering

  async function onSubmit(v: Form) {
    // D18: an engineering servicer never carries a section.
    const section_id = sectionDisabled ? null : v.section_id
    try {
      if (isEdit) {
        await onPatch?.({
          id: edit.id,
          section_id,
          assignment: v.assignment,
        })
        toast.success("Assignment updated")
      } else {
        await onCreate?.({
          account_id: v.account_id,
          section_id,
          assignment: v.assignment,
        })
        toast.success("Assignment added")
      }
      reset()
    } catch (e: any) {
      toast.error(
        e?.status === 422
          ? "owner/backup carries section accountability — a section is required (D12)"
          : e?.status === 409
            ? "That servicer already has an active owner assignment"
            : "Could not save assignment",
      )
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
      <div className="space-y-1.5">
        <Label>servicer</Label>
        <Controller
          control={control}
          name="account_id"
          render={({ field }) => (
            <ComboboxField
              options={servicers}
              value={field.value || null}
              placeholder="Select servicer…"
              emptyText="No servicers found"
              onChange={field.onChange}
            />
          )}
        />
        {!isEdit && errors.account_id && (
          <p className="text-destructive text-xs">
            {errors.account_id.message}
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label>role</Label>
        <Controller
          control={control}
          name="assignment"
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>{r}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
      </div>

      <div className="space-y-1.5">
        <Label className="flex items-center gap-1.5">
          section
          {sectionDisabled && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <LockIcon className="text-muted-foreground size-3.5" />
                </TooltipTrigger>
                <TooltipContent>
                  Engineering is skill-matched, not section-pooled (D18)
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </Label>
        <Controller
          control={control}
          name="section_id"
          render={({ field }) => (
            <Select
              // D18: engineering forces null and the control is disabled.
              value={sectionDisabled ? NO_SECTION : (field.value ?? NO_SECTION)}
              disabled={sectionDisabled}
              onValueChange={(v) =>
                field.onChange(v === NO_SECTION ? null : v)
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue
                  placeholder={
                    sectionDisabled
                      ? "Skill-matched — no section"
                      : "Select section…"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {/* Nullable section_id: the sentinel maps to null. zod's
                    refine still rejects this for owner/backup (D12). */}
                <SelectItem value={NO_SECTION}>— No section —</SelectItem>
                {sections.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        {!sectionDisabled && errors.section_id && (
          <p className="text-muted-foreground text-xs">
            {errors.section_id.message}
          </p>
        )}
      </div>

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting
          ? "Saving…"
          : submitLabel ?? (isEdit ? "Save changes" : "Add assignment")}
      </Button>
    </form>
  )
}
