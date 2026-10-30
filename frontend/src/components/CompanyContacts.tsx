import { Contact, Globe, Mail, Phone, Printer } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  CONTACT_GROUPS, contactHref, contactSourceLabel, getCompanyContacts,
  type ContactProfile,
} from "@/lib/companyContacts";

const icons = { phone: Phone, fax: Printer, email: Mail, website: Globe, other: Contact };

export function CompanyContacts({ profile }: { profile: ContactProfile }) {
  const contacts = getCompanyContacts(profile);
  if (!contacts.length) return null;

  return (
    <Card className="glass shadow-card border-accent/20">
      <CardHeader className="rounded-t-lg" style={{
        background: "linear-gradient(90deg, hsl(var(--accent) / 0.1) 0%, hsl(var(--secondary) / 0.1) 100%)",
      }}>
        <CardTitle className="text-foreground flex items-center gap-2 text-lg sm:text-xl">
          <span className="w-2 h-2 rounded-full bg-accent" aria-hidden="true" />
          Контактная информация
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Контакты из доступных источников. Источник не подтверждает актуальность контакта.
        </p>
      </CardHeader>
      <CardContent className="space-y-5 p-4 sm:p-6">
        {CONTACT_GROUPS.map(group => {
          const rows = contacts.filter(contact => contact.kind === group.kind);
          if (!rows.length) return null;
          const Icon = icons[group.kind];
          return (
            <section key={group.kind} aria-label={group.title}>
              <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{group.title}</h3>
              <ul className="divide-y divide-border rounded-xl border border-border/70 bg-card/40 px-3 sm:px-4">
                {rows.map(contact => {
                  const href = contactHref(contact);
                  const valueClass = "min-w-0 break-all text-sm font-semibold text-foreground sm:text-base";
                  return (
                    <li key={contact.key} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                      <div className="flex min-w-0 items-start gap-3">
                        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                        <div className="min-w-0">
                          {href ? (
                            <a href={href} className={`${valueClass} rounded-sm hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`}
                              {...(contact.kind === "website" ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
                              {contact.value}
                            </a>
                          ) : <span className={valueClass}>{contact.value}</span>}
                          {(contact.fullName || contact.position) && (
                            <p className="mt-1 break-words text-xs text-muted-foreground">
                              {[contact.fullName, contact.position].filter(Boolean).join(", ")}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 pl-7 sm:max-w-[45%] sm:justify-end sm:pl-0" aria-label="Источники контакта">
                        {contact.sources.length ? contact.sources.map(source => (
                          <Badge key={source} variant="outline" className="text-xs font-medium">
                            {contactSourceLabel(source)}
                          </Badge>
                        )) : <Badge variant="outline" className="text-xs font-medium">Источник не указан</Badge>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}
