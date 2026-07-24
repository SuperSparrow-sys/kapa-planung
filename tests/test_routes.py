

class TestPages:
    def test_index(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "Kapazit" in res.get_data(as_text=True)

    def test_partial(self, client):
        res = client.get("/_partial")
        assert res.status_code == 200
        data = res.get_json()
        assert "sidebar" in data
        assert "gantt" in data
        assert "quarter_options" in data
        assert "members" in data


class TestProjects:
    def test_create_list(self, client):
        res = client.post(
            "/api/projects",
            json={"name": "Testprojekt", "start_year": 2025, "start_q": 1, "duration": 2},
        )
        assert res.status_code == 200
        assert "id" in res.get_json()

    def test_create_no_name(self, client):
        res = client.post(
            "/api/projects",
            json={"name": "", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        assert res.status_code == 400

    def test_create_bad_quarter(self, client):
        res = client.post(
            "/api/projects",
            json={"name": "X", "start_year": 2025, "start_q": 5, "duration": 1},
        )
        assert res.status_code == 400

    def test_update_project(self, client):
        r = client.post(
            "/api/projects",
            json={"name": "Upd", "start_year": 2025, "start_q": 2, "duration": 3},
        )
        pid = r.get_json()["id"]
        res = client.patch(
            f"/api/projects/{pid}",
            json={"name": "Updated"},
        )
        assert res.status_code == 200

    def test_update_not_found(self, client):
        res = client.patch("/api/projects/99999", json={"name": "X"})
        assert res.status_code == 404

    def test_delete_project(self, client):
        r = client.post(
            "/api/projects",
            json={"name": "Del", "start_year": 2025, "start_q": 3, "duration": 1},
        )
        pid = r.get_json()["id"]
        res = client.delete(f"/api/projects/{pid}")
        assert res.status_code == 200

    def test_delete_not_found(self, client):
        res = client.delete("/api/projects/99999")
        assert res.status_code == 404


class TestSteps:
    def test_create_step(self, client):
        r = client.post(
            "/api/projects",
            json={"name": "Base", "start_year": 2025, "start_q": 1, "duration": 4},
        )
        pid = r.get_json()["id"]
        res = client.post(
            f"/api/projects/{pid}/steps",
            json={"name": "Step", "start_year": 2025, "start_q": 2, "duration": 1},
        )
        assert res.status_code == 200

    def test_create_step_no_project(self, client):
        res = client.post(
            "/api/projects/99999/steps",
            json={"name": "Step", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        assert res.status_code == 404

    def test_update_step(self, client):
        r = client.post(
            "/api/projects",
            json={"name": "B", "start_year": 2025, "start_q": 1, "duration": 4},
        )
        pid = r.get_json()["id"]
        r2 = client.post(
            f"/api/projects/{pid}/steps",
            json={"name": "S", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        sid = r2.get_json()["id"]
        res = client.patch(f"/api/steps/{sid}", json={"name": "S2"})
        assert res.status_code == 200

    def test_update_step_not_found(self, client):
        res = client.patch("/api/steps/99999", json={"name": "X"})
        assert res.status_code == 404

    def test_delete_step(self, client):
        r = client.post(
            "/api/projects",
            json={"name": "C", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        pid = r.get_json()["id"]
        r2 = client.post(
            f"/api/projects/{pid}/steps",
            json={"name": "Sd", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        sid = r2.get_json()["id"]
        res = client.delete(f"/api/steps/{sid}")
        assert res.status_code == 200


class TestMembers:
    def test_create_member(self, client):
        res = client.post(
            "/api/members",
            json={"name": "Neuer Mitarbeiter"},
        )
        assert res.status_code == 200

    def test_create_duplicate(self, client):
        client.post("/api/members", json={"name": "Dup"})
        res = client.post("/api/members", json={"name": "Dup"})
        assert res.status_code == 400

    def test_update_member(self, client):
        r = client.post("/api/members", json={"name": "UpdMe"})
        mid = r.get_json()["id"]
        res = client.patch(f"/api/members/{mid}", json={"max_stunden_quarter": 30})
        assert res.status_code == 200

    def test_update_not_found(self, client):
        res = client.patch("/api/members/99999", json={"name": "X"})
        assert res.status_code == 404

    def test_delete_member(self, client):
        r = client.post("/api/members", json={"name": "DelMe"})
        mid = r.get_json()["id"]
        res = client.delete(f"/api/members/{mid}")
        assert res.status_code == 200


class TestAllocations:
    def test_save_allocation(self, client):
        r_p = client.post(
            "/api/projects",
            json={"name": "AllocProj", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        pid = r_p.get_json()["id"]
        r_m = client.post("/api/members", json={"name": "AllocMem"})
        mid = r_m.get_json()["id"]

        res = client.post(
            "/api/allocations",
            json={
                "project_id": pid,
                "year": 2025,
                "quarter": 1,
                "values": {str(mid): 10.5},
            },
        )
        assert res.status_code == 200

    def test_bad_project(self, client):
        res = client.post(
            "/api/allocations",
            json={
                "project_id": 99999,
                "year": 2025,
                "quarter": 1,
                "values": {"1": 1},
            },
        )
        assert res.status_code == 404

    def test_bad_member(self, client):
        r_p = client.post(
            "/api/projects",
            json={"name": "Ap2", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        pid = r_p.get_json()["id"]
        res = client.post(
            "/api/allocations",
            json={
                "project_id": pid,
                "year": 2025,
                "quarter": 1,
                "values": {"99999": 5},
            },
        )
        assert res.status_code == 400

    def test_negative_stunden(self, client):
        r_p = client.post(
            "/api/projects",
            json={"name": "Ap3", "start_year": 2025, "start_q": 1, "duration": 1},
        )
        pid = r_p.get_json()["id"]
        r_m = client.post("/api/members", json={"name": "Am3"})
        mid = r_m.get_json()["id"]
        res = client.post(
            "/api/allocations",
            json={
                "project_id": pid,
                "year": 2025,
                "quarter": 1,
                "values": {str(mid): -1},
            },
        )
        assert res.status_code == 400

    def test_values_not_dict(self, client):
        res = client.post(
            "/api/allocations",
            json={
                "project_id": 1,
                "year": 2025,
                "quarter": 1,
                "values": "no_dict",
            },
        )
        assert res.status_code == 400


class TestRateLimit:
    def test_returns_200(self, client):
        for _ in range(30):
            res = client.get("/")
            assert res.status_code == 200
