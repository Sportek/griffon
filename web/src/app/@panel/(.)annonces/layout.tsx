import { SidePanel } from "@/components/panel/SidePanel";

/** A listing opened from another page: in the side panel, over that page. */
export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return <SidePanel>{children}</SidePanel>;
}
