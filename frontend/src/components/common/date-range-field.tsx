// src/components/common/date-range-field.tsx
import { CalendarIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover"

export type DateRange = { from?: Date; to?: Date }

const fmt = (d?: Date) => (d ? d.toISOString().slice(0, 10) : "—")

export function DateRangeField({
  value, onChange,
}: { value: DateRange; onChange: (r: DateRange) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline"
          className="w-full justify-start font-normal">
          <CalendarIcon className="mr-2 size-4" />
          {fmt(value.from)} → {fmt(value.to)}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar mode="range"
          selected={{ from: value.from, to: value.to }}
          onSelect={(r) => onChange({ from: r?.from, to: r?.to })}
          numberOfMonths={2} />
      </PopoverContent>
    </Popover>
  )
}
