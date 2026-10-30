export type Generation = {adapter?:string;model?:string;prompt_version?:string;review_required?:boolean};
export default function GenerationNotice({generation}:{generation?:Generation}){
 if(!generation?.adapter)return <p className="notice">Generation source was not recorded for this historical item. Review all claims and evidence before use.</p>;
 const test=generation.adapter.toLowerCase().includes('deterministic');
 return <aside className="notice"><strong>{test?'Deterministic test/development output':generation.adapter==='openai'?'OpenAI-backed output':'Evidence validation output'}</strong>{generation.model&&<small> · Model: {generation.model}</small>}<p>{test?'This item was produced by the test adapter, not a live OpenAI call.':'Model output and support checks can be wrong. Review the wording against the cited facts; neither is independent verification of your career history.'}</p></aside>;
}
