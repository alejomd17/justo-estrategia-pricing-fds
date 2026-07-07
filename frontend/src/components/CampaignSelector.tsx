import type { Campaign } from '../types'

interface Props {
  campaigns: Campaign[]
  selected: Campaign | null
  onChange: (c: Campaign) => void
}

export default function CampaignSelector({ campaigns, selected, onChange }: Props) {
  return (
    <select
      value={selected ? `${selected.CAMPAIGN_START}|${selected.CAMPAIGN_END}` : ''}
      onChange={(e) => {
        const [start, end] = e.target.value.split('|')
        const found = campaigns.find(
          (c) => c.CAMPAIGN_START === start && c.CAMPAIGN_END === end
        )
        if (found) onChange(found)
      }}
    >
      {campaigns.map((c) => {
        const key = `${c.CAMPAIGN_START}|${c.CAMPAIGN_END}`
        return (
          <option key={key} value={key}>
            {c.CAMPAIGN_START} - {c.CAMPAIGN_END}
          </option>
        )
      })}
    </select>
  )
}
