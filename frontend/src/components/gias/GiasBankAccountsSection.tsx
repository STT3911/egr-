import { Link } from "react-router-dom";
import { ArrowUpRight, Landmark } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CompanyGiasBankAccount } from "@/lib/api";

export const GiasBankAccountsSection = ({
  accounts,
  companyUnp,
}: {
  accounts: CompanyGiasBankAccount[];
  companyUnp: number;
}) => (
  <Card className="glass overflow-hidden border-sky-500/25 shadow-card">
    <CardHeader className="border-b border-border/60 bg-gradient-to-r from-sky-500/10 to-transparent p-4 sm:p-6">
      <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
        <Landmark className="h-5 w-5 text-sky-600 dark:text-sky-400" />
        Банковские реквизиты из договоров GIAS
        <span className="ml-auto rounded-full bg-sky-500/10 px-2.5 py-1 text-xs font-medium text-sky-700 dark:text-sky-300">
          {accounts.length}
        </span>
      </CardTitle>
    </CardHeader>
    <CardContent className="p-0">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Расчётный счёт</TableHead>
              <TableHead>Банк</TableHead>
              <TableHead>БИК</TableHead>
              <TableHead>Валюта</TableHead>
              <TableHead className="text-right">Источник</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accounts.map((account) => (
              <TableRow
                key={`${account.contract_id}-${account.account_number}-${account.bank_code}-${account.currency_code}`}
              >
                <TableCell className="font-mono font-medium">
                  {account.account_number || "—"}
                </TableCell>
                <TableCell>{account.bank_name || "—"}</TableCell>
                <TableCell className="font-mono">{account.bank_code || "—"}</TableCell>
                <TableCell>
                  {account.currency_name || account.currency_code || "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild size="sm" variant="ghost">
                    <Link
                      to={`/contracts/${account.contract_id}?fromUnp=${companyUnp}`}
                      aria-label="Открыть договор-источник"
                    >
                      Договор
                      <ArrowUpRight className="h-4 w-4" />
                    </Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </CardContent>
  </Card>
);
