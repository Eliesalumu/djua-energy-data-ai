from __future__ import annotations

from typing import Any


SCENARIOS: dict[str, dict[str, Any]] = {
    "bon": {
        "success": True,
        "data": {
            "client": {
                "accountNumber": "ACC-DEMO-0001",
                "firstName": "Jean-Luc",
                "lastName": "Kabila",
                "phone": "0848451555",
                "orangeMoneyAccountAgeMonths": 36,
                "estimatedIncomeUSD": 450,
                "profession": "Commercant independant",
                "historicalRiskScore": 0.12,
            },
            "subscription": {
                "kitId": "DJUA-KIN-000001",
                "offerName": "Orange Energie TV 24 + Fan",
                "status": "active",
                "paidMonthsCount": 16,
                "periodicAmountUSD": 25,
            },
            "paymentHistory": [
                {"paymentId": "TXN-1", "clientPhone": "0848451555", "amountUSD": 25, "date": "2026-08-01T12:00:00Z", "status": "completed"},
                {"paymentId": "TXN-2", "clientPhone": "0848451555", "amountUSD": 25, "date": "2026-07-01T12:00:00Z", "status": "completed"},
                {"paymentId": "TXN-3", "clientPhone": "0848451555", "amountUSD": 25, "date": "2026-06-01T12:00:00Z", "status": "completed"},
            ],
        },
    },
    "moyen": {
        "success": True,
        "data": {
            "client": {
                "accountNumber": "ACC-DEMO-0002",
                "firstName": "Aline",
                "lastName": "Mbuyi",
                "phone": "0847771122",
                "orangeMoneyAccountAgeMonths": 8,
                "estimatedIncomeUSD": 170,
                "profession": "Vendeur de rue",
                "historicalRiskScore": 0.46,
            },
            "subscription": {
                "kitId": "DJUA-MAS-000222",
                "offerName": "Orange Energie Gold Basic",
                "status": "active",
                "paidMonthsCount": 4,
                "periodicAmountUSD": 20,
            },
            "paymentHistory": [
                {"paymentId": "TXN-4", "clientPhone": "0847771122", "amountUSD": 20, "date": "2026-07-10T12:00:00Z", "status": "completed"},
                {"paymentId": "TXN-5", "clientPhone": "0847771122", "amountUSD": 20, "date": "2026-06-18T12:00:00Z", "status": "late"},
                {"paymentId": "TXN-6", "clientPhone": "0847771122", "amountUSD": 20, "date": "2026-05-12T12:00:00Z", "status": "completed"},
            ],
        },
    },
    "risque": {
        "success": True,
        "data": {
            "client": {
                "accountNumber": "ACC-DEMO-0003",
                "firstName": "Tresor",
                "lastName": "Manioki",
                "phone": "0849991122",
                "orangeMoneyAccountAgeMonths": 3,
                "estimatedIncomeUSD": 95,
                "profession": "Sans emploi",
                "historicalRiskScore": 0.82,
            },
            "subscription": {
                "kitId": "DJUA-MAS-000999",
                "offerName": "Orange Energie Gold Basic",
                "status": "suspended",
                "paidMonthsCount": 1,
                "periodicAmountUSD": 15,
            },
            "paymentHistory": [
                {"paymentId": "TXN-7", "clientPhone": "0849991122", "amountUSD": 15, "date": "2026-04-03T12:00:00Z", "status": "completed"},
                {"paymentId": "TXN-8", "clientPhone": "0849991122", "amountUSD": 15, "date": "2026-05-03T12:00:00Z", "status": "missed"},
                {"paymentId": "TXN-9", "clientPhone": "0849991122", "amountUSD": 15, "date": "2026-06-03T12:00:00Z", "status": "failed"},
            ],
        },
    },
}
