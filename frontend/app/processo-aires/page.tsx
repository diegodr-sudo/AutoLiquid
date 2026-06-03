"use client";

import { Fragment, useMemo, useState } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, FileSearch, Loader2, Search } from "lucide-react";
import Link from "next/link";
import { Header } from "@/components/header";
import { GlassButton } from "@/components/glass-card";
import { Input } from "@/components/ui/input";
import { analisarProcessoAiresDev, type AiresProcessoAnaliseResult } from "@/lib/data";

const PDF_EXEMPLOS = [
  "/Users/diegodutraramos/Downloads/FATURA_251430__CENTRO_DE_CIÊNCIAS_FÍSICAS_E_MATEMÁTICAS_-_CFM.pdf",
  "/Users/diegodutraramos/Downloads/FATURA_251433_assinado.pdf",
];

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value || 0);
}

function normalizarProcesso(valor: string): string {
  const digits = valor.replace(/\D/g, "");
  if (digits.length <= 5) return digits;
  return `${digits.slice(0, 5)}/${digits.slice(5, 7)}`;
}

type FornecedorDetalhe = {
  numeroFatura: string;
  nome: string;
  tarifa: number;
  irpj_24: number;
  csll_1: number;
};

type FornecedorAgrupado = {
  cnpj: string;
  nome: string;
  tarifa: number;
  irpj_24: number;
  csll_1: number;
  detalhes: FornecedorDetalhe[];
};

type ConcessionariaDetalhe = {
  numeroFatura: string;
  nome: string;
  baseTaxa: number;
  retTaxa: number;
};

type ConcessionariaAgrupada = {
  cnpj: string;
  nome: string;
  baseTaxa: number;
  retTaxa: number;
  detalhes: ConcessionariaDetalhe[];
};

function agruparFornecedores(resultado: AiresProcessoAnaliseResult | null): FornecedorAgrupado[] {
  const porCnpj = new Map<string, FornecedorAgrupado>();

  for (const fatura of resultado?.faturas ?? []) {
    for (const fornecedor of fatura.fornecedores ?? []) {
      const cnpj = fornecedor.cnpj || "Sem CNPJ";
      const atual = porCnpj.get(cnpj) ?? {
        cnpj,
        nome: fornecedor.nome || "",
        tarifa: 0,
        irpj_24: 0,
        csll_1: 0,
        detalhes: [],
      };

      atual.nome ||= fornecedor.nome || "";
      atual.tarifa += fornecedor.tarifa || 0;
      atual.irpj_24 += fornecedor.irpj_24 || 0;
      atual.csll_1 += fornecedor.csll_1 || 0;

      const numeroFatura = fatura.numeroFatura || "-";
      const detalhe = atual.detalhes.find((item) => item.numeroFatura === numeroFatura);
      if (detalhe) {
        detalhe.tarifa += fornecedor.tarifa || 0;
        detalhe.irpj_24 += fornecedor.irpj_24 || 0;
        detalhe.csll_1 += fornecedor.csll_1 || 0;
      } else {
        atual.detalhes.push({
          numeroFatura,
          nome: fornecedor.nome || "",
          tarifa: fornecedor.tarifa || 0,
          irpj_24: fornecedor.irpj_24 || 0,
          csll_1: fornecedor.csll_1 || 0,
        });
      }

      porCnpj.set(cnpj, atual);
    }
  }

  return Array.from(porCnpj.values()).sort((a, b) => a.cnpj.localeCompare(b.cnpj, "pt-BR"));
}

function agruparConcessionarias(resultado: AiresProcessoAnaliseResult | null): ConcessionariaAgrupada[] {
  const porCnpj = new Map<string, ConcessionariaAgrupada>();

  for (const fatura of resultado?.faturas ?? []) {
    for (const concessionaria of fatura.concessionarias ?? []) {
      const cnpj = concessionaria.cnpj || "Sem CNPJ";
      const atual = porCnpj.get(cnpj) ?? {
        cnpj,
        nome: concessionaria.nome || "",
        baseTaxa: 0,
        retTaxa: 0,
        detalhes: [],
      };

      atual.nome ||= concessionaria.nome || "";
      atual.baseTaxa += concessionaria.base_taxa || 0;
      atual.retTaxa += concessionaria.ret_taxa || 0;

      const numeroFatura = fatura.numeroFatura || "-";
      const detalhe = atual.detalhes.find((item) => item.numeroFatura === numeroFatura);
      if (detalhe) {
        detalhe.baseTaxa += concessionaria.base_taxa || 0;
        detalhe.retTaxa += concessionaria.ret_taxa || 0;
      } else {
        atual.detalhes.push({
          numeroFatura,
          nome: concessionaria.nome || "",
          baseTaxa: concessionaria.base_taxa || 0,
          retTaxa: concessionaria.ret_taxa || 0,
        });
      }

      porCnpj.set(cnpj, atual);
    }
  }

  return Array.from(porCnpj.values()).sort((a, b) => a.cnpj.localeCompare(b.cnpj, "pt-BR"));
}

export default function ProcessoAiresPage() {
  const [numeroProcesso, setNumeroProcesso] = useState("");
  const [usarExemplos, setUsarExemplos] = useState(false);
  const [resultado, setResultado] = useState<AiresProcessoAnaliseResult | null>(null);
  const [fornecedorExpandido, setFornecedorExpandido] = useState<string | null>(null);
  const [concessionariaExpandida, setConcessionariaExpandida] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const fornecedoresAgrupados = useMemo(() => agruparFornecedores(resultado), [resultado]);
  const concessionariasAgrupadas = useMemo(() => agruparConcessionarias(resultado), [resultado]);

  const analisar = async () => {
    const processo = normalizarProcesso(numeroProcesso);
    if (!processo) {
      setErro("Informe o número do processo.");
      return;
    }
    setCarregando(true);
    setErro("");
    setResultado(null);
    try {
      const data = await analisarProcessoAiresDev(processo, {
        pdfPaths: usarExemplos ? PDF_EXEMPLOS : [],
        extrairPecasSolar: !usarExemplos,
      });
      setResultado(data);
      setFornecedorExpandido(null);
      setConcessionariaExpandida(null);
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível analisar o processo AIRES.");
    } finally {
      setCarregando(false);
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />

      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-orange-700">
              Laboratório dev
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Processo AIRES</h2>
          </div>
          <Link
            href="/?dev=1"
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-glass-border bg-background px-3 text-sm font-medium text-muted-foreground transition hover:bg-secondary/50 hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Link>
        </div>

        <section className="rounded-2xl border border-glass-border bg-glass-bg p-4 shadow-[0_28px_80px_-48px_rgba(15,23,42,0.4)]">
          <div className="grid gap-3 md:grid-cols-[minmax(220px,320px)_auto_auto_minmax(0,1fr)] md:items-end">
            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Número do processo
              </span>
              <Input
                value={numeroProcesso}
                onChange={(event) => {
                  setNumeroProcesso(normalizarProcesso(event.target.value));
                  setErro("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void analisar();
                }}
                placeholder="26684/26"
                className="h-11 rounded-lg bg-background"
              />
            </label>

            <label className="inline-flex h-11 items-center gap-2 rounded-lg border border-glass-border bg-background px-3 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={usarExemplos}
                onChange={(event) => setUsarExemplos(event.target.checked)}
                className="h-4 w-4"
              />
              Usar PDFs de exemplo
            </label>

            <GlassButton
              type="button"
              onClick={analisar}
              disabled={carregando || !numeroProcesso.trim()}
              className="h-11"
            >
              {carregando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {carregando ? "Analisando..." : "Consultar"}
            </GlassButton>

            <div className="min-h-5 text-sm">
              {erro ? (
                <p className="text-destructive">{erro}</p>
              ) : resultado ? (
                <p className="text-muted-foreground">{resultado.mensagem}</p>
              ) : (
                <p className="text-muted-foreground">A análise identifica faturas AIRES pelo conteúdo do PDF.</p>
              )}
            </div>
          </div>
        </section>

        {resultado ? (
          <>
            <section className="grid gap-3 md:grid-cols-3">
              {[
                ["Faturas", resultado.totais.faturas],
                ["Fornecedores", resultado.totais.fornecedores],
                ["Concessionárias", resultado.totais.concessionarias],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-glass-border bg-background/80 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
                </div>
              ))}
            </section>

            {resultado.pecasFatura.length ? (
              <section className="rounded-2xl border border-glass-border bg-background/80 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Peças localizadas</p>
                <div className="mt-3 grid gap-2">
                  {resultado.pecasFatura.map((peca, index) => (
                    <div key={`${peca.titulo}-${index}`} className="rounded-lg border border-glass-border bg-muted/20 px-3 py-2 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="truncate font-medium">{peca.titulo}</p>
                        {peca.status ? (
                          <span className="rounded-full border border-glass-border bg-background px-2 py-0.5 text-xs uppercase tracking-wider text-muted-foreground">
                            {peca.status}
                          </span>
                        ) : null}
                      </div>
                      {peca.numeroFatura ? (
                        <p className="mt-1 text-xs text-muted-foreground">Fatura {peca.numeroFatura}</p>
                      ) : null}
                      {peca.erro ? <p className="mt-1 text-xs text-destructive">{peca.erro}</p> : null}
                      {peca.arquivoUrl || peca.href ? (
                        <p className="mt-1 truncate text-xs text-muted-foreground">{peca.arquivoUrl || peca.href}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {fornecedoresAgrupados.length ? (
              <section className="rounded-2xl border border-glass-border bg-background/80 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-700">
                      Fornecedores
                    </p>
                    <h3 className="mt-1 text-lg font-semibold">Retenções agrupadas por CNPJ</h3>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Clique em uma linha para ver a origem por fatura.
                  </p>
                </div>

                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[720px] text-left text-sm">
                    <thead className="border-b border-glass-border text-xs uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="w-9 py-2 pr-3" aria-label="Expandir" />
                        <th className="py-2 pr-3">CNPJ</th>
                        <th className="py-2 pr-3 text-right">Tarifa</th>
                        <th className="py-2 pr-3 text-right">6256 (2,40%)</th>
                        <th className="py-2 pr-3 text-right">6228 (1,00%)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-glass-border/60">
                      {fornecedoresAgrupados.map((item) => {
                        const aberto = fornecedorExpandido === item.cnpj;
                        return (
                          <Fragment key={item.cnpj}>
                            <tr
                              onClick={() => setFornecedorExpandido(aberto ? null : item.cnpj)}
                              className="cursor-pointer transition hover:bg-secondary/35"
                            >
                              <td className="py-2 pr-3 text-muted-foreground">
                                {aberto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              </td>
                              <td className="py-2 pr-3">
                                <p className="font-mono text-xs font-medium">{item.cnpj}</p>
                                {item.nome ? <p className="mt-0.5 text-xs text-muted-foreground">{item.nome}</p> : null}
                              </td>
                              <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(item.tarifa)}</td>
                              <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(item.irpj_24)}</td>
                              <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(item.csll_1)}</td>
                            </tr>
                            {aberto ? (
                              <tr>
                                <td />
                                <td colSpan={4} className="py-3 pr-3">
                                  <div className="rounded-xl border border-glass-border bg-muted/20">
                                    <table className="w-full text-left text-xs">
                                      <thead className="border-b border-glass-border text-muted-foreground">
                                        <tr>
                                          <th className="px-3 py-2">Fatura</th>
                                          <th className="px-3 py-2">Fornecedor</th>
                                          <th className="px-3 py-2 text-right">Tarifa</th>
                                          <th className="px-3 py-2 text-right">6256</th>
                                          <th className="px-3 py-2 text-right">6228</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-glass-border/50">
                                        {item.detalhes
                                          .sort((a, b) => a.numeroFatura.localeCompare(b.numeroFatura, "pt-BR"))
                                          .map((detalhe) => (
                                            <tr key={`${item.cnpj}-${detalhe.numeroFatura}`}>
                                              <td className="px-3 py-2 font-mono">{detalhe.numeroFatura}</td>
                                              <td className="px-3 py-2">{detalhe.nome || item.nome || "-"}</td>
                                              <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(detalhe.tarifa)}</td>
                                              <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(detalhe.irpj_24)}</td>
                                              <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(detalhe.csll_1)}</td>
                                            </tr>
                                          ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </td>
                              </tr>
                            ) : null}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}

            {concessionariasAgrupadas.length ? (
              <section className="rounded-2xl border border-glass-border bg-background/80 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-700">
                      Concessionárias
                    </p>
                    <h3 className="mt-1 text-lg font-semibold">Taxas agrupadas por CNPJ</h3>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Clique em uma linha para ver a origem por fatura.
                  </p>
                </div>

                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[680px] text-left text-sm">
                    <thead className="border-b border-glass-border text-xs uppercase tracking-wider text-muted-foreground">
                      <tr>
                        <th className="w-9 py-2 pr-3" aria-label="Expandir" />
                        <th className="py-2 pr-3">CNPJ</th>
                        <th className="py-2 pr-3 text-right">Base taxa</th>
                        <th className="py-2 pr-3 text-right">6175 (7,05%)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-glass-border/60">
                      {concessionariasAgrupadas.map((item) => {
                        const aberto = concessionariaExpandida === item.cnpj;
                        return (
                          <Fragment key={item.cnpj}>
                            <tr
                              onClick={() => setConcessionariaExpandida(aberto ? null : item.cnpj)}
                              className="cursor-pointer transition hover:bg-secondary/35"
                            >
                              <td className="py-2 pr-3 text-muted-foreground">
                                {aberto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              </td>
                              <td className="py-2 pr-3">
                                <p className="font-mono text-xs font-medium">{item.cnpj}</p>
                                {item.nome ? <p className="mt-0.5 text-xs text-muted-foreground">{item.nome}</p> : null}
                              </td>
                              <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(item.baseTaxa)}</td>
                              <td className="py-2 pr-3 text-right tabular-nums">{formatCurrency(item.retTaxa)}</td>
                            </tr>
                            {aberto ? (
                              <tr>
                                <td />
                                <td colSpan={3} className="py-3 pr-3">
                                  <div className="rounded-xl border border-glass-border bg-muted/20">
                                    <table className="w-full text-left text-xs">
                                      <thead className="border-b border-glass-border text-muted-foreground">
                                        <tr>
                                          <th className="px-3 py-2">Fatura</th>
                                          <th className="px-3 py-2">Concessionária</th>
                                          <th className="px-3 py-2 text-right">Base taxa</th>
                                          <th className="px-3 py-2 text-right">6175</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-glass-border/50">
                                        {item.detalhes
                                          .sort((a, b) => a.numeroFatura.localeCompare(b.numeroFatura, "pt-BR"))
                                          .map((detalhe) => (
                                            <tr key={`${item.cnpj}-${detalhe.numeroFatura}`}>
                                              <td className="px-3 py-2 font-mono">{detalhe.numeroFatura}</td>
                                              <td className="px-3 py-2">{detalhe.nome || item.nome || "-"}</td>
                                              <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(detalhe.baseTaxa)}</td>
                                              <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(detalhe.retTaxa)}</td>
                                            </tr>
                                          ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </td>
                              </tr>
                            ) : null}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}

            {resultado.faturas.map((fatura) => (
              <section key={`${fatura.numeroFatura}-${fatura.origem}`} className="rounded-2xl border border-glass-border bg-background/80 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Fatura</p>
                    <h3 className="mt-1 flex items-center gap-2 text-lg font-semibold">
                      <FileSearch className="h-5 w-5 text-orange-700" />
                      {fatura.numeroFatura}
                    </h3>
                  </div>
                  <div className="text-right text-sm text-muted-foreground">
                    <p>{fatura.emissao || "-"} · venc. {fatura.vencimento || "-"}</p>
                    <p className="truncate">{fatura.periodo || fatura.origem}</p>
                  </div>
                </div>

              </section>
            ))}
          </>
        ) : null}
      </div>
    </main>
  );
}
