import { cookieBands } from "./Patch";

test("equal cookies give equal 8-band stripes; one changed byte changes exactly one band", () => {
  const a = cookieBands("00ab12cd34ef5678");
  expect(a).toHaveLength(8);
  expect(cookieBands("0x00ab12cd34ef5678")).toEqual(a);
  const b = cookieBands("00ab12cd34ef5679")!;
  expect(b.filter((v, i) => v !== a![i])).toHaveLength(1);
});

test("short cookies are left-padded and an empty cookie has no stripe", () => {
  expect(cookieBands("ff")).toEqual(cookieBands("00000000000000ff"));
  expect(cookieBands(null)).toBeNull();
});

test("a zero cookie means 'not signed': no stripe, so an unsigned rule is never drawn as a solid colour bar", () => {
  expect(cookieBands("0000000000000000")).toBeNull();
  expect(cookieBands("0x0")).toBeNull();
});
